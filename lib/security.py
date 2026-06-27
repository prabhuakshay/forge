"""Security scanning for the audit gate: known-vulnerable dependencies and
risky code patterns, run through the project's own tools.

Two scans, both optional and both graceful when the tool isn't installed (forge
never imposes a dependency — it offers a hint to add one):

  * dependencies — `pip-audit` against the resolved environment, surfacing CVEs
    with their fix versions. These are concrete and actionable, so a finding is a
    *blocking* audit problem (override loudly if a CVE has no fix yet).
  * code — `bandit`, surfacing risky patterns (shell=True, weak crypto, …). These
    need triage and have false positives, so findings are *advisory warnings* by
    default; set FORGE_SECURITY_STRICT=1 to make high-severity code findings block.

Tools are invoked via `uv run` (project venv, no activation) when uv is present,
mirroring lib.gate. The JSON parsers are pure functions so they're unit-testable
without the tools installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field

_TIMEOUT = 300


@dataclass
class ScanResult:
    tool: str
    available: bool  # the tool could be invoked at all
    completed: bool  # it ran to completion (a finding is completion, not failure)
    findings: list[str] = field(default_factory=list)
    note: str = ""  # hint (tool missing) or explanation (could not complete)


def strict() -> bool:
    """True when the project opts code findings into blocking the gate."""
    return os.environ.get("FORGE_SECURITY_STRICT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _runner() -> list[str]:
    return ["uv", "run"] if shutil.which("uv") else []


def _available(project_dir: str, tool: str) -> bool:
    """Whether `tool` can be invoked in the project (probed with --version)."""
    runner = _runner()
    if not runner and shutil.which(tool) is None:
        return False
    try:
        proc = subprocess.run(
            [*runner, tool, "--version"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def parse_pip_audit(stdout: str) -> list[str]:
    """Extract one finding line per vulnerable dependency from pip-audit JSON.

    Handles both the object form (`{"dependencies": [...]}`) and the legacy bare
    list form. A dependency with an empty `vulns` list is clean and skipped."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    deps = data.get("dependencies", []) if isinstance(data, dict) else data
    findings: list[str] = []
    for dep in deps if isinstance(deps, list) else []:
        if not isinstance(dep, dict):
            continue
        vulns = dep.get("vulns") or []
        for v in vulns:
            ident = v.get("id", "?")
            fixes = v.get("fix_versions") or []
            fix = f"fix: {', '.join(fixes)}" if fixes else "no fix available"
            findings.append(
                f"{dep.get('name', '?')} {dep.get('version', '?')}: {ident} ({fix})"
            )
    return findings


def parse_bandit(stdout: str, high_only: bool) -> list[str]:
    """Extract finding lines from bandit JSON. When `high_only`, keep just
    HIGH-severity/HIGH-confidence issues (the blocking set); otherwise keep
    MEDIUM and above (the advisory set). LOW noise is always dropped."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    results = data.get("results", []) if isinstance(data, dict) else []
    findings: list[str] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        sev = str(r.get("issue_severity", "")).upper()
        conf = str(r.get("issue_confidence", "")).upper()
        if high_only:
            if not (sev == "HIGH" and conf == "HIGH"):
                continue
        elif sev not in {"MEDIUM", "HIGH"}:
            continue
        loc = f"{r.get('filename', '?')}:{r.get('line_number', '?')}"
        findings.append(
            f"{loc} [{sev}/{conf}] {r.get('test_id', '?')}: {r.get('issue_text', '')}"
        )
    return findings


def scan_dependencies(project_dir: str) -> ScanResult:
    """Run pip-audit and report vulnerable dependencies."""
    if not _available(project_dir, "pip-audit"):
        return ScanResult(
            "pip-audit",
            available=False,
            completed=False,
            note="pip-audit not installed — `uv add --group dev pip-audit` "
            "to scan dependencies for known CVEs.",
        )
    cmd = [*_runner(), "pip-audit", "--format", "json"]
    try:
        proc = subprocess.run(
            cmd, cwd=project_dir, capture_output=True, text=True, timeout=_TIMEOUT
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return ScanResult(
            "pip-audit", available=True, completed=False, note=f"could not run: {exc}"
        )
    findings = parse_pip_audit(proc.stdout)
    # pip-audit exits non-zero precisely when it finds vulnerabilities, so a
    # non-zero code with parsed findings is a *successful* scan, not a tool error.
    if not findings and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:300]
        return ScanResult(
            "pip-audit",
            available=True,
            completed=False,
            note=f"did not complete cleanly: {detail}",
        )
    return ScanResult("pip-audit", available=True, completed=True, findings=findings)


def _bandit_target(project_dir: str) -> tuple[list[str], list[str]]:
    """The path(s) bandit should scan and the dirs to exclude. Prefer a `src/`
    layout; otherwise scan the project root, excluding noise (venv, tests, build,
    vcs) so the scan is about first-party code, not dependencies or fixtures."""
    if os.path.isdir(os.path.join(project_dir, "src")):
        return ["src"], []
    excludes = [
        "./.venv",
        "./venv",
        "./tests",
        "./build",
        "./dist",
        "./.git",
        "./.forge",
    ]
    return ["."], excludes


def scan_code(project_dir: str) -> ScanResult:
    """Run bandit and report risky code patterns (severity per strict mode)."""
    if not _available(project_dir, "bandit"):
        return ScanResult(
            "bandit",
            available=False,
            completed=False,
            note="bandit not installed — `uv add --group dev bandit` "
            "to scan code for risky patterns.",
        )
    targets, excludes = _bandit_target(project_dir)
    cmd = [*_runner(), "bandit", "-r", *targets, "-f", "json", "-q"]
    if excludes:
        cmd += ["-x", ",".join(excludes)]
    try:
        proc = subprocess.run(
            cmd, cwd=project_dir, capture_output=True, text=True, timeout=_TIMEOUT
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return ScanResult(
            "bandit", available=True, completed=False, note=f"could not run: {exc}"
        )
    # bandit exits non-zero when it finds issues; JSON on stdout is what matters.
    if not proc.stdout.strip():
        detail = (proc.stderr or "").strip()[:300]
        return ScanResult(
            "bandit",
            available=True,
            completed=False,
            note=f"produced no report: {detail}",
        )
    findings = parse_bandit(proc.stdout, high_only=strict())
    return ScanResult("bandit", available=True, completed=True, findings=findings)
