"""Integration tests for the commit/push/plan gate hooks.

Each test runs the real `python hooks/scripts/<hook>.py` process, feeds it the
event JSON Claude Code would send on stdin, and asserts on the decision it prints
and on the on-disk state it leaves behind. Covers mark_dirty and the PreToolUse
gates (require_check, require_audit, require_plan), including the hardened
command parsing. The context/format/stop hooks live in test_hooks_context.py.
"""

from __future__ import annotations

import os

from conftest import run_hook, write
from lib import state


def _at(project: str, rel: str) -> str:
    """Absolute path of `rel` inside `project` — hooks receive absolute paths."""
    return os.path.join(project, rel)


# --- mark_dirty (PostToolUse) --------------------------------------------


def test_mark_dirty_records_py_edit(project):
    write(project, "src/app.py", "x = 1\n")
    state.record_pass(project, "check")  # establish a green to be invalidated

    run = run_hook(
        "mark_dirty",
        {"cwd": project, "tool_input": {"file_path": _at(project, "src/app.py")}},
    )

    assert run.code == 0
    assert state.dirty_files(project) == ["src/app.py"]
    assert not state.is_current(project, "check")  # green dropped


def test_mark_dirty_doc_edit_is_not_dirty_code(project):
    run_hook(
        "mark_dirty",
        {"cwd": project, "tool_input": {"file_path": _at(project, "README.md")}},
    )
    assert state.dirty_files(project) == []


def test_mark_dirty_ignores_non_forge_project(tmp_path):
    proj = str(tmp_path)  # no .forge/
    run_hook("mark_dirty", {"cwd": proj, "tool_input": {"file_path": f"{proj}/a.py"}})
    assert not os.path.exists(os.path.join(proj, ".forge"))


# --- require_check (PreToolUse / git commit) -----------------------------


def _commit(project):
    return {"cwd": project, "tool_input": {"command": "git commit -m 'x'"}}


def test_commit_blocked_when_not_green(project):
    run = run_hook("require_check", _commit(project))
    assert run.decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_commit_allowed_when_green(project):
    write(project, "src/app.py", "x = 1\n")
    state.record_pass(project, "check")
    run = run_hook("require_check", _commit(project))
    assert run.decision is None and run.code == 0


def test_non_commit_command_is_ignored(project):
    run = run_hook(
        "require_check", {"cwd": project, "tool_input": {"command": "ls -la"}}
    )
    assert run.decision is None


def test_commit_override_is_consumed_and_logged(project):
    write(project, ".forge/override-check", "hotfix: prod down")
    run = run_hook("require_check", _commit(project))

    assert run.decision is None  # allowed
    assert not os.path.exists(_at(project, ".forge/override-check"))  # consumed
    overrides = state.load(project)["overrides"]
    assert overrides[-1]["gate"] == "check"
    assert overrides[-1]["reason"] == "hotfix: prod down"


# --- require_audit (PreToolUse / push & publish) -------------------------


def test_push_blocked_when_audit_not_green(project):
    run = run_hook(
        "require_audit",
        {"cwd": project, "tool_input": {"command": "git push origin main"}},
    )
    assert run.decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_publish_blocked_when_audit_not_green(project):
    run = run_hook(
        "require_audit", {"cwd": project, "tool_input": {"command": "uv publish"}}
    )
    assert run.decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_push_allowed_when_audit_green(project):
    state.record_pass(project, "audit")
    run = run_hook(
        "require_audit",
        {"cwd": project, "tool_input": {"command": "git push origin main"}},
    )
    assert run.decision is None and run.code == 0


# --- hardened parsing, end to end through the real hook ------------------


def test_commit_with_global_C_option_is_blocked(project):
    """`git -C <path> commit` — the path isn't a flag, so the old regex lost the
    subcommand and waved it through. It must now be caught."""
    run = run_hook(
        "require_check",
        {"cwd": project, "tool_input": {"command": "git -C /repo commit -m x"}},
    )
    assert run.decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_commit_message_mentioning_push_does_not_trip_audit(project):
    """A commit whose message contains 'git push' must NOT be blocked by the
    push/publish guard (the old regex false-positived here). audit is left not
    green so a false match would surface as a deny."""
    run = run_hook(
        "require_audit",
        {
            "cwd": project,
            "tool_input": {"command": "git commit -m 'implement git push retry'"},
        },
    )
    assert run.decision is None  # allowed: it's a commit, not a push


def test_push_via_nested_shell_is_blocked(project):
    run = run_hook(
        "require_audit",
        {"cwd": project, "tool_input": {"command": "bash -c 'git push origin main'"}},
    )
    assert run.decision["hookSpecificOutput"]["permissionDecision"] == "deny"


# --- require_plan (PreToolUse / source edits) ----------------------------


def _edit_src(project):
    return {"cwd": project, "tool_input": {"file_path": _at(project, "src/feature.py")}}


def test_source_edit_blocked_without_plan(project):
    run = run_hook("require_plan", _edit_src(project))
    assert run.decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_source_edit_allowed_with_plan_file(project):
    write(project, "docs/plans/feature.md", "- [ ] do the thing")
    run = run_hook("require_plan", _edit_src(project))
    assert run.decision is None


def test_non_source_edit_is_allowed(project):
    run = run_hook(
        "require_plan",
        {"cwd": project, "tool_input": {"file_path": _at(project, "scripts/tool.py")}},
    )
    assert run.decision is None  # not under src/, so unscoped


def test_plan_override_allows_edit(project):
    write(project, ".forge/override-plan", "trivial typo")
    run = run_hook("require_plan", _edit_src(project))
    assert run.decision is None
    assert not os.path.exists(_at(project, ".forge/override-plan"))
