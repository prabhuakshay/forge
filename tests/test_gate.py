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

    # Pretend uv is on PATH so the runner prefix is deterministic.
    monkeypatch.setattr(gate.shutil, "which", lambda tool: "/usr/bin/uv")
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


def test_run_skips_missing_tool_without_uv(monkeypatch):
    """No uv and the tool absent → skipped, not a hard failure (graceful on a
    half-initialised repo)."""
    monkeypatch.setattr(gate.shutil, "which", lambda tool: None)
    step = gate.run_lint("/proj")
    assert step.skipped and not step.ok
