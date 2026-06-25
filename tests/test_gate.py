"""Tests for the gate runner — result aggregation and mypy path scoping.

The actual tools (ruff/mypy/pytest) aren't invoked; we monkeypatch the subprocess
boundary so we can assert exactly what command the gate would run, in particular
that the Stop gate's dirty-file scoping reaches mypy."""

from __future__ import annotations

import types

from lib import gate
from lib.gate import GateResult, StepResult


def test_gateresult_ok_and_failures():
    r = GateResult(
        [
            StepResult("ruff", [], ok=True, skipped=False, output=""),
            StepResult("mypy", [], ok=False, skipped=False, output="boom"),
            StepResult("pytest", [], ok=False, skipped=True, output="n/a"),
        ]
    )
    assert not r.ok  # a real failure present
    assert [s.name for s in r.failures()] == ["mypy"]  # skipped != failure


def test_gateresult_ok_when_only_skips():
    r = GateResult([StepResult("mypy", [], ok=False, skipped=True, output="")])
    assert r.ok


def test_summary_marks_each_step():
    r = GateResult(
        [
            StepResult("a", [], ok=True, skipped=False, output=""),
            StepResult("b", [], ok=False, skipped=False, output=""),
            StepResult("c", [], ok=False, skipped=True, output=""),
        ]
    )
    summary = r.summary()
    assert "✓ a" in summary and "✗ b" in summary and "— c" in summary


def _capture_cmd(monkeypatch):
    """Make gate._run capture the command instead of spawning a process."""
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    # Pretend uv is on PATH so the runner prefix is deterministic, and that the
    # project configures mypy so run_types actually invokes it (its detection is
    # exercised separately below).
    monkeypatch.setattr(gate.shutil, "which", lambda tool: "/usr/bin/uv")
    monkeypatch.setattr(gate, "_uses_mypy", lambda project_dir: True)
    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    return seen


def test_run_types_defaults_to_whole_tree(monkeypatch):
    seen = _capture_cmd(monkeypatch)
    gate.run_types("/proj")
    assert seen[0] == ["uv", "run", "mypy", "."]


def test_run_types_scopes_to_given_paths(monkeypatch):
    seen = _capture_cmd(monkeypatch)
    gate.run_types("/proj", paths=["src/a.py", "src/b.py"])
    assert seen[0] == ["uv", "run", "mypy", "src/a.py", "src/b.py"]


def test_run_fast_passes_type_paths_through(monkeypatch):
    seen = _capture_cmd(monkeypatch)
    gate.run_fast("/proj", type_paths=["src/a.py"])
    # last command is the mypy step, scoped to the dirty file
    assert seen[-1] == ["uv", "run", "mypy", "src/a.py"]


def test_run_marks_step_failed_on_timeout(monkeypatch):
    """A hung tool must surface as a real failure (not a skip), so the gate goes
    red rather than silently passing — and the message names the timeout."""
    monkeypatch.setattr(gate.shutil, "which", lambda tool: "/usr/bin/uv")

    def boom(cmd, **kwargs):
        raise gate.subprocess.TimeoutExpired(cmd, 600)

    monkeypatch.setattr(gate.subprocess, "run", boom)
    step = gate.run_lint("/proj")
    assert not step.ok and not step.skipped
    assert "timed out" in step.output


def test_run_full_aggregates_all_four_steps(monkeypatch):
    _capture_cmd(monkeypatch)
    result = gate.run_full("/proj")
    assert [s.name for s in result.steps] == [
        "ruff format",
        "ruff check",
        "mypy",
        "pytest",
    ]
    assert result.ok  # every fake step returns 0


def test_run_fast_skips_the_test_step(monkeypatch):
    _capture_cmd(monkeypatch)
    result = gate.run_fast("/proj")
    # format + lint + types, but no pytest — the cheap "is the tree broken?" check.
    assert [s.name for s in result.steps] == ["ruff format", "ruff check", "mypy"]


def test_run_skips_missing_tool_without_uv(monkeypatch):
    """No uv and the tool absent → skipped, not a hard failure (graceful on a
    half-initialised repo)."""
    monkeypatch.setattr(gate.shutil, "which", lambda tool: None)
    step = gate.run_lint("/proj")
    assert step.skipped and not step.ok


# --- mypy is opt-in by configuration --------------------------------------


def test_run_types_skips_when_project_has_no_mypy_config(tmp_path):
    """A project that doesn't configure mypy must not be failed on a tool it
    doesn't use — the step is skipped, not red."""
    step = gate.run_types(str(tmp_path))
    assert step.skipped and not step.ok
    assert "no mypy configuration" in step.output


def test_run_types_runs_when_pyproject_declares_mypy(monkeypatch, tmp_path):
    """With real detection (no _uses_mypy override), a `[tool.mypy]` table makes
    the type step actually invoke mypy rather than skip."""
    (tmp_path / "pyproject.toml").write_text('[tool.mypy]\npython_version = "3.10"\n')
    seen: list[list[str]] = []
    monkeypatch.setattr(gate.shutil, "which", lambda tool: "/usr/bin/uv")
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda cmd, **kw: (
            seen.append(cmd)
            or types.SimpleNamespace(returncode=0, stdout="", stderr="")
        ),
    )
    gate.run_types(str(tmp_path))
    assert seen == [["uv", "run", "mypy", "."]]


def test_uses_mypy_detects_each_config_source(tmp_path):
    assert not gate._uses_mypy(str(tmp_path))  # nothing configured
    (tmp_path / "mypy.ini").write_text("[mypy]\n")
    assert gate._uses_mypy(str(tmp_path))


def test_uses_mypy_detects_setup_cfg_section(tmp_path):
    (tmp_path / "setup.cfg").write_text("[metadata]\nname = x\n\n[mypy]\n")
    assert gate._uses_mypy(str(tmp_path))


# --- coverage floor: respect a project's own setting ----------------------


def test_run_tests_applies_default_floor_when_project_has_none(monkeypatch, tmp_path):
    seen = _capture_cmd(monkeypatch)
    gate.run_tests(str(tmp_path))  # no pyproject.toml at all
    assert f"--cov-fail-under={gate.COVERAGE_FAIL_UNDER}" in seen[0]


def test_run_tests_omits_floor_when_project_sets_fail_under(monkeypatch, tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage.report]\nfail_under = 95\n"
    )
    seen = _capture_cmd(monkeypatch)
    gate.run_tests(str(tmp_path))
    # We must not override (and thereby lower) the project's stricter floor.
    assert not any(a.startswith("--cov-fail-under") for a in seen[0])


def test_run_tests_omits_floor_when_addopts_sets_it(monkeypatch, tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov=pkg --cov-fail-under=90"\n'
    )
    seen = _capture_cmd(monkeypatch)
    gate.run_tests(str(tmp_path))
    assert not any(a.startswith("--cov-fail-under") for a in seen[0])


def test_run_tests_ignores_commented_or_misplaced_floor(monkeypatch, tmp_path):
    """A `--cov-fail-under` in a comment, or a `fail_under` outside
    `[tool.coverage.report]`, must NOT read as the project setting its own floor —
    otherwise forge would silently drop its default on a project that never set one."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        "# addopts = '--cov-fail-under=90'  # disabled, just a note\n"
        "[tool.ruff]\n"
        'fail_under = "not a coverage setting"\n'
    )
    seen = _capture_cmd(monkeypatch)
    gate.run_tests(str(tmp_path))
    assert f"--cov-fail-under={gate.COVERAGE_FAIL_UNDER}" in seen[0]


# --- configurable subprocess timeout --------------------------------------


def test_timeout_defaults_to_600(monkeypatch):
    monkeypatch.delenv("FORGE_GATE_TIMEOUT", raising=False)
    assert gate._timeout() == 600


def test_timeout_honours_env_override(monkeypatch):
    monkeypatch.setenv("FORGE_GATE_TIMEOUT", "30")
    assert gate._timeout() == 30


def test_timeout_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("FORGE_GATE_TIMEOUT", "not-a-number")
    assert gate._timeout() == 600
