"""Integration tests for the require_review commit gate (option B).

Review only gates `git commit` where the project has something binding to enforce:
a recorded directive, or an installed reference governing a changed file. Each test
runs the real hook process the way Claude Code does (see conftest.run_hook) and
asserts on the decision plus the on-disk state it leaves behind.
"""

from __future__ import annotations

import os
import subprocess

from conftest import run_hook, write
from lib import state

_DIRECTIVE = "- CLI MUST use subcommands. (see docs/decisions/0001-cli.md)\n"


def _commit(project: str) -> dict:
    return {"cwd": project, "tool_input": {"command": "git commit -m 'x'"}}


def _denied(run) -> bool:
    return (
        run.decision is not None
        and run.decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    )


def _git_init(project: str) -> None:
    subprocess.run(["git", "-C", project, "init", "-q"], check=True)


# --- option B: the gate is inactive with nothing binding to enforce ------


def test_review_gate_inactive_without_binding_rules(project):
    # No directives, no references → nothing for review to bind, so commit is the
    # require_check hook's business alone; require_review stays out of the way.
    run = run_hook("require_review", _commit(project))
    assert run.decision is None and run.code == 0


def test_template_only_directives_do_not_activate_gate(project):
    # The scaffolded directives.md is prose with no recorded bullets — that must
    # not count as a binding decision, or every forge project would be gated.
    write(
        project,
        ".forge/directives.md",
        "# Binding directives — demo\n\nprose only\n\n<!-- appended below -->\n",
    )
    run = run_hook("require_review", _commit(project))
    assert run.decision is None and run.code == 0


# --- the directive half of option B --------------------------------------


def test_commit_blocked_when_directives_unreviewed(project):
    write(project, ".forge/directives.md", _DIRECTIVE)
    run = run_hook("require_review", _commit(project))
    assert _denied(run)
    reason = run.decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert "review" in reason


def test_commit_allowed_when_review_green(project):
    write(project, ".forge/directives.md", _DIRECTIVE)
    state.record_pass(project, "review")  # clean review recorded for this tree
    run = run_hook("require_review", _commit(project))
    assert run.decision is None and run.code == 0


def test_non_commit_command_is_ignored(project):
    write(project, ".forge/directives.md", _DIRECTIVE)
    run = run_hook(
        "require_review", {"cwd": project, "tool_input": {"command": "ls -la"}}
    )
    assert run.decision is None


def test_review_override_consumed_and_logged(project):
    write(project, ".forge/directives.md", _DIRECTIVE)
    write(project, ".forge/override-review", "ship now, review forward")
    run = run_hook("require_review", _commit(project))

    assert run.decision is None  # allowed
    assert not os.path.exists(
        os.path.join(project, ".forge/override-review")
    )  # consumed
    overrides = state.load(project)["overrides"]
    assert overrides[-1]["gate"] == "review"
    assert overrides[-1]["reason"] == "ship now, review forward"


def test_ignores_non_forge_project(tmp_path):
    proj = str(tmp_path)  # no .forge/
    run = run_hook("require_review", _commit(proj))
    assert run.decision is None and run.code == 0


# --- the reference half of option B (needs a real repo for `git status`) -


def test_commit_blocked_when_reference_governs_changed_file(project):
    _git_init(project)
    write(
        project,
        ".forge/references/python-base.md",
        '---\nname: python-base\napplies_to: ["src/**/*.py"]\nenforcement: blocking\n---\nrules\n',
    )
    write(project, "src/app.py", "x = 1\n")  # untracked, governed by the reference
    run = run_hook("require_review", _commit(project))
    assert _denied(run)


def test_commit_allowed_when_reference_governs_nothing_changed(project):
    # A reference is installed but governs no changed file (only a doc changed),
    # so option B leaves the gate inactive.
    _git_init(project)
    write(
        project,
        ".forge/references/python-base.md",
        '---\nname: python-base\napplies_to: ["src/**/*.py"]\nenforcement: blocking\n---\nrules\n',
    )
    write(project, "notes.md", "hello\n")  # untracked, not governed
    run = run_hook("require_review", _commit(project))
    assert run.decision is None and run.code == 0
