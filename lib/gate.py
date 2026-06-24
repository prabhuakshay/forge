"""Run the code quality gate by shelling out to the project's own tools.

This module deliberately does NOT import ruff/mypy/pytest. They live in the
target project's environment, at the project's pinned versions; the plugin must
not impose its own. We invoke them through `uv run` when available (so the
project venv is used without activation) and fall back to a bare invocation
otherwise. Every step is captured structurally so a command or a hook can decide
what to do with the failures.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

# The "balanced" default coverage floor. It is applied ONLY when the project
# hasn't declared its own (see _project_sets_cov_floor) — passing it
# unconditionally would override, and could silently *lower*, a stricter project
# setting, which is the opposite of what a quality gate should do.
COVERAGE_FAIL_UNDER = 80

# Per-step subprocess timeout (seconds). A hung tool must not wedge a hook
# forever, but a large suite can legitimately run long, so the ceiling is
# overridable per project via the FORGE_GATE_TIMEOUT environment variable.
_DEFAULT_TIMEOUT = 600


def _timeout() -> int:
    try:
        return max(1, int(os.environ.get("FORGE_GATE_TIMEOUT", str(_DEFAULT_TIMEOUT))))
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT


def _project_sets_cov_floor(project_dir: str) -> bool:
    """True when the project already declares its own coverage floor.

    A forge-scaffolded project pins `fail_under` in `[tool.coverage.report]`; a
    mature one may raise it. In that case forge must NOT pass its own
    `--cov-fail-under`, because the CLI flag overrides the config file and would
    silently replace the project's floor with our default. Detected by reading
    pyproject.toml as text — tomllib is 3.11+, and forge targets 3.10 — looking
    for a `fail_under =` line or a `--cov-fail-under` already wired into addopts.
    """
    try:
        with open(os.path.join(project_dir, "pyproject.toml"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    return (
        bool(re.search(r"(?m)^\s*fail_under\s*=", text)) or "--cov-fail-under" in text
    )


def _uses_mypy(project_dir: str) -> bool:
    """True when the project configures mypy, so the type step should run.

    Type-checking is opt-in by configuration. A project that sets mypy up — a
    `[tool.mypy]` table in pyproject.toml, a `mypy.ini`/`.mypy.ini`, or a `[mypy]`
    section in setup.cfg — gets type-checked; one that doesn't is not forced to.
    Without this guard, `uv run mypy` on a project that never installed mypy would
    *fail* the gate (uv can't find the tool) rather than skip it, leaving a
    non-mypy project permanently red on a tool it deliberately doesn't use. A
    forge-scaffolded project ships `[tool.mypy]`, so it keeps type-checking; any
    project can opt in the same way (an empty `[tool.mypy]` is enough)."""
    for fname in ("mypy.ini", ".mypy.ini"):
        if os.path.exists(os.path.join(project_dir, fname)):
            return True
    for fname, pattern in (
        ("pyproject.toml", r"(?m)^\s*\[tool\.mypy"),
        ("setup.cfg", r"(?m)^\s*\[mypy\]"),
    ):
        try:
            with open(os.path.join(project_dir, fname), encoding="utf-8") as fh:
                if re.search(pattern, fh.read()):
                    return True
        except OSError:
            continue
    return False


@dataclass
class StepResult:
    name: str
    cmd: list[str]
    ok: bool
    skipped: bool
    output: str


@dataclass
class GateResult:
    steps: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok or s.skipped for s in self.steps)

    def failures(self) -> list[StepResult]:
        return [s for s in self.steps if not s.ok and not s.skipped]

    def summary(self) -> str:
        lines = []
        for s in self.steps:
            mark = "—" if s.skipped else ("✓" if s.ok else "✗")
            lines.append(f"  {mark} {s.name}")
        return "\n".join(lines)


def _runner() -> list[str]:
    """Prefix that runs a tool inside the project environment.

    `uv run` resolves the project venv without needing it activated, which is
    what we want from a non-interactive hook. Without uv we fall back to running
    the tool directly and let _run() treat a missing binary as 'skipped'.
    """
    if shutil.which("uv"):
        return ["uv", "run"]
    return []


def _run(project_dir: str, name: str, tool_args: list[str]) -> StepResult:
    runner = _runner()
    cmd = runner + tool_args
    tool = tool_args[0]
    # If we're not going through `uv run`, a missing tool means the project
    # simply isn't set up for it yet — skip rather than hard-fail, so the gate
    # degrades gracefully on a half-initialised repo.
    if not runner and shutil.which(tool) is None:
        return StepResult(
            name,
            cmd,
            ok=False,
            skipped=True,
            output=f"{tool} not found on PATH; skipped",
        )
    try:
        proc = subprocess.run(
            cmd, cwd=project_dir, capture_output=True, text=True, timeout=_timeout()
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return StepResult(
            name, cmd, ok=proc.returncode == 0, skipped=False, output=out.strip()
        )
    except FileNotFoundError:
        return StepResult(
            name, cmd, ok=False, skipped=True, output=f"{tool} unavailable; skipped"
        )
    except subprocess.TimeoutExpired:
        return StepResult(
            name,
            cmd,
            ok=False,
            skipped=False,
            output=f"{name} timed out after {_timeout()}s",
        )


def run_format_check(project_dir: str) -> StepResult:
    return _run(project_dir, "ruff format", ["ruff", "format", "--check", "."])


def run_lint(project_dir: str) -> StepResult:
    return _run(project_dir, "ruff check", ["ruff", "check", "."])


def run_types(project_dir: str, paths: list[str] | None = None) -> StepResult:
    """Type-check the whole tree, or only `paths` when given.

    Scoping to changed files keeps the Stop hook's every-turn check proportional
    to the edit rather than to repo size. mypy still follows imports out of those
    files, so a cross-file error they introduce is caught — what we skip is the
    cost of re-checking modules nothing touched.

    Skipped (not failed) when the project doesn't configure mypy — see
    _uses_mypy — so the gate degrades gracefully on a non-type-checked project."""
    if not _uses_mypy(project_dir):
        return StepResult(
            "mypy",
            ["mypy"],
            ok=False,
            skipped=True,
            output="no mypy configuration found; type check skipped",
        )
    targets = list(paths) if paths else ["."]
    return _run(project_dir, "mypy", ["mypy", *targets])


def run_tests(project_dir: str, cov: bool = True) -> StepResult:
    args = ["pytest", "-q"]
    if cov and not _project_sets_cov_floor(project_dir):
        # Impose forge's default floor only when the project hasn't set its own,
        # so we never override (or silently lower) a stricter project config.
        args += [f"--cov-fail-under={COVERAGE_FAIL_UNDER}"]
    return _run(project_dir, "pytest", args)


def run_full(project_dir: str, cov: bool = True) -> GateResult:
    """The complete code gate, in fail-fast-friendly order: cheap/fast checks
    first (format, lint, types) so a typo surfaces before the slow test run."""
    result = GateResult()
    result.steps.append(run_format_check(project_dir))
    result.steps.append(run_lint(project_dir))
    result.steps.append(run_types(project_dir))
    result.steps.append(run_tests(project_dir, cov=cov))
    return result


def run_fast(project_dir: str, type_paths: list[str] | None = None) -> GateResult:
    """Format + lint + types, no tests — for the Stop hook, where we want a quick
    'did you leave the tree broken?' signal without paying for the suite.

    `type_paths` scopes the mypy step (None = whole tree). The Stop hook passes
    the dirty set so types are re-checked only where the agent edited; format and
    lint stay whole-tree because ruff is fast enough that scoping isn't worth the
    chance of missing drift it would otherwise catch."""
    result = GateResult()
    result.steps.append(run_format_check(project_dir))
    result.steps.append(run_lint(project_dir))
    result.steps.append(run_types(project_dir, type_paths))
    return result
