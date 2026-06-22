#!/usr/bin/env python3
"""CLI entrypoint for the mechanical half of /forge:audit.

Covers everything checkable without judgement: config sync, lockfile sync,
scaffolding completeness, and metadata agreement. The *doc↔code* half is the
doc-sync-auditor agent, which the command runs separately — this script does NOT
record an audit pass, because audit is only green when both halves are.

Exit status: 0 = no mechanical problems, 1 = problems found (printed).
"""

import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import env_scan  # noqa: E402

REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    ".gitignore",
    ".env.example",
    "CHANGELOG.md",
    "pyproject.toml",
]


def _check_env(project: str, problems: list[str], warnings: list[str]) -> None:
    drift = env_scan.analyse(project)
    if drift.undocumented:
        problems.append(
            "Undocumented env vars (read in code, missing from .env.example): "
            + ", ".join(drift.undocumented)
        )
    if drift.stale:
        warnings.append(
            "Stale env vars (in .env.example, not read in code): "
            + ", ".join(drift.stale)
        )


def _check_scaffolding(project: str, problems: list[str]) -> None:
    for rel in REQUIRED_FILES:
        if not os.path.exists(os.path.join(project, rel)):
            problems.append(f"Missing expected file: {rel}")
    if not os.path.isdir(os.path.join(project, "docs")):
        problems.append("Missing docs/ directory")


def _check_lockfile(project: str, problems: list[str], warnings: list[str]) -> None:
    if not os.path.exists(os.path.join(project, "uv.lock")):
        warnings.append("No uv.lock — run `uv lock` to pin dependencies.")
        return
    if shutil.which("uv") is None:
        return
    try:
        proc = subprocess.run(
            ["uv", "lock", "--check"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            problems.append(
                "uv.lock is out of sync with pyproject.toml (run `uv lock`)."
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _check_metadata(project: str, warnings: list[str]) -> None:
    """Light agreement check: requires-python vs mypy's python_version.

    Stays a warning, not a failure: parsing is regex-based and a mismatch is
    worth surfacing but rarely worth blocking a release over on its own.
    """
    try:
        text = open(os.path.join(project, "pyproject.toml"), encoding="utf-8").read()
    except OSError:
        return
    req = re.search(r'requires-python\s*=\s*"[^0-9]*([0-9]+\.[0-9]+)', text)
    myp = re.search(r'python_version\s*=\s*"([0-9]+\.[0-9]+)"', text)
    if req and myp and req.group(1) != myp.group(1):
        warnings.append(
            f"Python version mismatch: requires-python {req.group(1)} vs "
            f"mypy python_version {myp.group(1)}."
        )


def main() -> int:
    project = os.getcwd()
    problems: list[str] = []
    warnings: list[str] = []

    _check_env(project, problems, warnings)
    _check_scaffolding(project, problems)
    _check_lockfile(project, problems, warnings)
    _check_metadata(project, warnings)

    print("forge audit (mechanical)")
    for w in warnings:
        print(f"  ! {w}")
    for p in problems:
        print(f"  ✗ {p}")

    if not problems:
        print(
            "\nMechanical audit clean. "
            "Now run the doc-sync auditor to complete the audit."
        )
        return 0
    print(f"\n{len(problems)} problem(s) must be fixed before the audit can pass.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
