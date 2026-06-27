"""Tests for the bin/ CLI entrypoints the slash-commands invoke.

These drive each script as a real subprocess (the way the commands do), feeding
stdin and reading the exit code + stdout, and assert the on-disk side effects.
Tools the gate would shell out to (uv/ruff/mypy/pytest) are kept off PATH so the
gate degrades to "skipped" and the entrypoint behaviour is deterministic."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from conftest import PLUGIN_ROOT, write
from lib import state

BIN_DIR = os.path.join(PLUGIN_ROOT, "bin")


def run_bin(
    script: str,
    args: tuple[str, ...] = (),
    cwd: str = ".",
    stdin: str = "",
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, os.path.join(BIN_DIR, f"{script}.py"), *args],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=cwd,
        env=env if env is not None else os.environ.copy(),
        timeout=60,
    )


def _toolless_env(tmp_path) -> dict:
    """An env whose PATH has no uv/ruff/mypy/pytest, so the gate skips every step
    (and check.py therefore goes green without a real toolchain present)."""
    empty = tmp_path / "emptybin"
    empty.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(empty)
    return env


# --- check.py -------------------------------------------------------------


def test_check_records_pass_when_gate_is_green(project, tmp_path):
    proc = run_bin("check", cwd=project, env=_toolless_env(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GREEN" in proc.stdout
    # The pass is recorded against the current tree, so the commit gate is now
    # satisfied for it.
    assert state.is_current(project, "check")


# --- mark.py --------------------------------------------------------------


def test_mark_records_named_gate(project):
    proc = run_bin("mark", ("audit",), cwd=project)
    assert proc.returncode == 0
    assert state.is_current(project, "audit")


def test_mark_rejects_unknown_gate(project):
    proc = run_bin("mark", ("nonsense",), cwd=project)
    assert proc.returncode == 2
    assert "usage" in proc.stderr.lower()


# --- plan.py --------------------------------------------------------------


def test_plan_sets_active_plan(project):
    proc = run_bin("plan", ("active", "docs/plans/0002-thing.md"), cwd=project)
    assert proc.returncode == 0, proc.stderr
    assert state.load(project)["active_plan"] == "docs/plans/0002-thing.md"


def test_plan_rejects_bad_usage(project):
    proc = run_bin("plan", ("bogus",), cwd=project)
    assert proc.returncode == 2
    assert "usage" in proc.stderr.lower()
    assert state.load(project).get("active_plan") is None


# --- audit.py -------------------------------------------------------------


def _scaffold(project: str) -> None:
    for rel in (
        "README.md",
        "LICENSE",
        ".gitignore",
        ".env.example",
        "CHANGELOG.md",
        "pyproject.toml",
    ):
        write(project, rel, "")
    os.makedirs(os.path.join(project, "docs"), exist_ok=True)


def test_audit_clean_project_passes(project):
    _scaffold(project)
    proc = run_bin("audit", cwd=project)
    assert proc.returncode == 0, proc.stdout
    assert "clean" in proc.stdout.lower()


def test_audit_flags_missing_required_file(project):
    _scaffold(project)
    os.remove(os.path.join(project, "LICENSE"))
    proc = run_bin("audit", cwd=project)
    assert proc.returncode == 1
    assert "LICENSE" in proc.stdout


def test_audit_flags_undocumented_env_var(project):
    _scaffold(project)
    write(project, "src/app.py", 'import os\nx = os.getenv("SECRET_TOKEN")\n')
    proc = run_bin("audit", cwd=project)
    assert proc.returncode == 1
    assert "SECRET_TOKEN" in proc.stdout


# --- refs.py --------------------------------------------------------------


def test_refs_available_lists_library(project):
    proc = run_bin("refs", ("available",), cwd=project)
    assert proc.returncode == 0
    # The shipped library carries the django reference.
    assert "django" in proc.stdout


def test_refs_installed_and_applicable(project):
    write(
        project,
        ".forge/references/django.md",
        '---\nname: django\napplies_to: ["**/models.py"]\nenforcement: blocking\n---\nrules\n',
    )
    installed = run_bin("refs", ("installed",), cwd=project)
    assert installed.returncode == 0 and "django" in installed.stdout

    applicable = run_bin("refs", ("applicable", "app/models.py"), cwd=project)
    assert applicable.returncode == 0 and "django" in applicable.stdout

    none = run_bin("refs", ("applicable", "app/utils.py"), cwd=project)
    assert none.returncode == 0 and "(none)" in none.stdout


def test_refs_unknown_subcommand(project):
    proc = run_bin("refs", ("bogus",), cwd=project)
    assert proc.returncode == 2


# --- decide.py ------------------------------------------------------------


_DRAFT = {
    "title": "Use uv for dependencies",
    "context": "We need one dependency manager.",
    "decision": "All deps go through uv.",
    "rationale": "Reproducible, fast, single lockfile.",
    "directive": "Manage every dependency with uv (never pip).",
    "date": "2026-06-24",
}


def test_decide_writes_adr_and_directive(project):
    proc = run_bin("decide", cwd=project, stdin=json.dumps(_DRAFT))
    assert proc.returncode == 0, proc.stderr
    adr = os.path.join(project, "docs", "decisions", "0001-use-uv-for-dependencies.md")
    assert os.path.exists(adr)
    with open(adr, encoding="utf-8") as fh:
        assert "Use uv for dependencies" in fh.read()
    with open(os.path.join(project, ".forge", "directives.md"), encoding="utf-8") as fh:
        assert "Manage every dependency with uv" in fh.read()


def test_decide_rejects_missing_fields(project):
    draft = dict(_DRAFT)
    del draft["rationale"]
    proc = run_bin("decide", cwd=project, stdin=json.dumps(draft))
    assert proc.returncode == 1
    assert "rationale" in proc.stderr


def test_decide_rejects_invalid_json(project):
    proc = run_bin("decide", cwd=project, stdin="{not json")
    assert proc.returncode == 1
    assert "Invalid JSON" in proc.stderr


# --- doc_claims.py --------------------------------------------------------


def test_doc_claims_emits_valid_json(project):
    write(project, "README.md", "# Project\n\nRun `forge` to start.\n")
    os.makedirs(os.path.join(project, "docs"), exist_ok=True)
    proc = run_bin("doc_claims", cwd=project)
    assert proc.returncode == 0
    json.loads(proc.stdout)  # must be parseable structured output


# --- status.py ------------------------------------------------------------


def test_status_reports_on_a_fresh_project(project):
    proc = run_bin("status", cwd=project)
    assert proc.returncode == 0, proc.stderr
    assert "forge status" in proc.stdout
    assert "never run" in proc.stdout


# --- override.py ----------------------------------------------------------


def test_override_arms_named_gate(project):
    proc = run_bin("override", ("check", "urgent", "hotfix"), cwd=project)
    assert proc.returncode == 0, proc.stderr
    assert "Armed" in proc.stdout
    # The sentinel the gate consumes is on disk, carrying the joined reason.
    assert state.pending_overrides(project) == {"check": "urgent hotfix"}


def test_override_rejects_unknown_gate(project):
    proc = run_bin("override", ("bogus",), cwd=project)
    assert proc.returncode == 2
    assert "usage" in proc.stderr.lower()
    assert state.pending_overrides(project) == {}


def test_override_list_shows_history(project):
    state.log_override(project, "check", "first bypass")
    proc = run_bin("override", ("list",), cwd=project)
    assert proc.returncode == 0
    assert "first bypass" in proc.stdout


def test_override_list_empty(project):
    proc = run_bin("override", ("list",), cwd=project)
    assert proc.returncode == 0
    assert "No overrides" in proc.stdout


def test_override_prune_keeps_recent(project):
    for i in range(4):
        state.log_override(project, "check", f"r{i}")
    proc = run_bin("override", ("prune", "1"), cwd=project)
    assert proc.returncode == 0
    assert "Pruned 3" in proc.stdout
    assert [e["reason"] for e in state.load(project)["overrides"]] == ["r3"]


def test_override_prune_rejects_bad_count(project):
    proc = run_bin("override", ("prune", "lots"), cwd=project)
    assert proc.returncode == 2
    assert "usage" in proc.stderr.lower()
