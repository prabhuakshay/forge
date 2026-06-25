"""Integration tests for the context-injecting and tree-state hooks.

Companion to test_hooks_integration.py (which covers the commit/push/plan gates);
here we cover the SessionStart/edit-time context injection (load_directives,
inject_reference) and the file-state hooks (auto_format, stop_gate). Same harness:
each test runs the real `python hooks/scripts/<hook>.py` process. External tools
are shadowed by the `faketools` fixture where a hook shells out.
"""

from __future__ import annotations

import os

from conftest import run_hook, write
from lib import state


def _at(project: str, rel: str) -> str:
    """Absolute path of `rel` inside `project` — hooks receive absolute paths."""
    return os.path.join(project, rel)


# --- load_directives (SessionStart) --------------------------------------


def test_session_start_injects_directives_and_reference_index(project):
    write(project, ".forge/directives.md", "- CLI MUST use subcommands.")
    write(
        project,
        ".forge/references/django.md",
        "---\nname: django\nsummary: Django rules\napplies_to: "
        '["**/models.py"]\nenforcement: blocking\n---\n- Fat models.',
    )
    run = run_hook("load_directives", {"cwd": project})

    ctx = run.decision["hookSpecificOutput"]["additionalContext"]
    assert "CLI MUST use subcommands." in ctx
    assert "django [blocking]" in ctx


def test_session_start_injects_nothing_when_empty(project):
    run = run_hook("load_directives", {"cwd": project})
    assert run.decision is None  # no directives, no references → no noise


# --- inject_reference (PreToolUse) ---------------------------------------

_DJANGO_REF = (
    "---\nname: django\nsummary: Django rules\napplies_to: "
    '["**/models.py"]\nenforcement: blocking\n---\n- Fat models, thin views.'
)


def test_reference_injected_when_editing_governed_file(project):
    write(project, ".forge/references/django.md", _DJANGO_REF)
    run = run_hook(
        "inject_reference",
        {
            "cwd": project,
            "session_id": "s1",
            "tool_input": {"file_path": _at(project, "models.py")},
        },
    )
    ctx = run.decision["hookSpecificOutput"]["additionalContext"]
    assert "Fat models, thin views." in ctx


def test_reference_injected_only_once_per_session(project):
    write(project, ".forge/references/django.md", _DJANGO_REF)
    payload = {
        "cwd": project,
        "session_id": "s1",
        "tool_input": {"file_path": _at(project, "models.py")},
    }
    first = run_hook("inject_reference", payload)
    second = run_hook("inject_reference", payload)  # same session
    assert first.decision is not None
    assert second.decision is None  # suppressed the second time


def test_reference_not_injected_for_ungoverned_file(project):
    write(project, ".forge/references/django.md", _DJANGO_REF)
    run = run_hook(
        "inject_reference",
        {
            "cwd": project,
            "session_id": "s1",
            "tool_input": {"file_path": _at(project, "utils.py")},
        },
    )
    assert run.decision is None


# --- auto_format (PostToolUse) -------------------------------------------


def test_auto_format_runs_ruff_on_the_edited_file(project, faketools):
    path = write(project, "src/app.py", "x=1\n")
    run = run_hook(
        "auto_format",
        {"cwd": project, "tool_input": {"file_path": path}},
        env=faketools.env(),
    )
    assert run.code == 0
    log = faketools.log()
    assert f"ruff format {path}" in log
    assert f"ruff check --fix {path}" in log


def test_auto_format_ignores_non_python(project, faketools):
    path = write(project, "README.md", "hi")
    run_hook(
        "auto_format",
        {"cwd": project, "tool_input": {"file_path": path}},
        env=faketools.env(),
    )
    assert not faketools.invoked("ruff")


def test_auto_format_ignores_non_forge_project(tmp_path, faketools):
    """Scoped to forge projects like every other hook: a .py edit in a repo with
    no .forge/ must not trigger ruff (no silent formatting outside the workflow)."""
    proj = tmp_path / "plain"
    proj.mkdir()
    path = write(str(proj), "app.py", "x=1\n")
    run = run_hook(
        "auto_format",
        {"cwd": str(proj), "tool_input": {"file_path": path}},
        env=faketools.env(),
    )
    assert run.code == 0
    assert not faketools.invoked("ruff")


# --- stop_gate (Stop) ----------------------------------------------------


def test_stop_blocks_on_type_error_in_dirty_file(project, faketools):
    # The type step is opt-in by config, so a type-checked project declares mypy.
    write(project, "pyproject.toml", "[tool.mypy]\n")
    write(project, "src/app.py", "x = 1\n")
    state.add_dirty(project, "src/app.py")
    run = run_hook(
        "stop_gate", {"cwd": project}, env=faketools.env(ruff_exit=0, mypy_exit=1)
    )
    assert run.decision["decision"] == "block"
    assert "mypy" in run.decision["reason"]


def test_stop_allows_clean_tree(project, faketools):
    write(project, "src/app.py", "x = 1\n")
    state.add_dirty(project, "src/app.py")
    run = run_hook(
        "stop_gate", {"cwd": project}, env=faketools.env(ruff_exit=0, mypy_exit=0)
    )
    assert run.decision is None and run.code == 0


def test_stop_skips_mypy_when_nothing_dirty(project, faketools):
    """The performance win: a turn that touched no .py pays zero mypy cost."""
    write(project, "src/app.py", "x = 1\n")  # exists but not in the dirty set
    run = run_hook("stop_gate", {"cwd": project}, env=faketools.env())
    assert run.decision is None
    assert not faketools.invoked("mypy")  # never even invoked


def test_stop_blocks_on_env_drift(project, faketools):
    write(project, "src/app.py", 'import os\nKEY = os.getenv("SECRET_KEY")\n')
    # dirty set empty → mypy skipped; the only problem is the undocumented var.
    run = run_hook("stop_gate", {"cwd": project}, env=faketools.env(ruff_exit=0))
    assert run.decision["decision"] == "block"
    assert "SECRET_KEY" in run.decision["reason"]


def test_stop_override_releases_even_when_broken(project, faketools):
    write(project, "src/app.py", "x = 1\n")
    state.add_dirty(project, "src/app.py")
    write(project, ".forge/override-stop", "deliberate WIP")
    run = run_hook(
        "stop_gate", {"cwd": project}, env=faketools.env(ruff_exit=1, mypy_exit=1)
    )
    assert run.decision is None  # override honoured
    assert not os.path.exists(_at(project, ".forge/override-stop"))  # consumed


def test_stop_ignores_non_forge_project(tmp_path, faketools):
    run = run_hook("stop_gate", {"cwd": str(tmp_path)}, env=faketools.env(mypy_exit=1))
    assert run.decision is None and run.code == 0
