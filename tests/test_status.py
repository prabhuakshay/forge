"""Tests for the /forge:status report builder (lib/status.report).

The report is a pure function over the state/refs/decisions layers, so we drive
it by setting those up on a throwaway project and asserting on the rendered text.
"""

from __future__ import annotations

from conftest import write
from lib import state, status


def test_report_shows_never_run_gates_on_empty_project(project):
    out = status.report(project)
    assert "forge status" in out
    assert "check  (commit gate): never run" in out
    assert "audit  (push/publish gate): never run" in out


def test_report_marks_green_then_stale(project):
    write(project, "src/app.py", "x = 1\n")
    state.record_pass(project, "check")
    assert "check  (commit gate): green" in status.report(project)

    # Editing source invalidates the fingerprint → the same gate now reads stale.
    write(project, "src/app.py", "x = 2\n")
    stale = status.report(project)
    assert "check  (commit gate): stale" in stale
    assert "re-run /forge:check" in stale


def test_report_lists_dirty_files(project):
    write(project, "src/a.py", "")
    state.add_dirty(project, "src/a.py")
    out = status.report(project)
    assert "dirty since last check (1)" in out
    assert "src/a.py" in out


def test_report_surfaces_armed_and_logged_overrides(project):
    state.request_override(project, "check", "hotfix")
    out = status.report(project)
    assert "armed overrides (1)" in out
    assert "check — hotfix" in out

    # Once consumed, it moves from "armed" to the logged history.
    state.take_override(project, "check")
    done = status.report(project)
    assert "armed overrides" not in done
    assert "override history (1)" in done


def test_report_lists_references_and_directives(project):
    write(
        project,
        ".forge/references/django.md",
        '---\nname: django\napplies_to: ["**/models.py"]\nenforcement: blocking\n---\nrules\n',
    )
    write(project, ".forge/directives.md", "- Always use uv.\n- Subcommand CLIs.\n")
    out = status.report(project)
    assert "style references (1)" in out
    assert "django [blocking] — **/models.py" in out
    assert "directives   2 binding" in out
