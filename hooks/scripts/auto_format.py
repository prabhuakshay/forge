"""PostToolUse hook: silently format and safe-fix a just-edited Python file.

Runs `ruff format` then `ruff check --fix` (safe fixes only) on the single file
that was touched. Scoped to one file so it's instant and never reformats code the
agent didn't touch. Unsafe fixes are deliberately excluded — they can change
behaviour, and a format-on-save hook must never alter semantics behind your back.

Always exits 0: a formatting failure should not block the edit that triggered it.
"""

import os
import shutil
import subprocess

import _bootstrap  # noqa: F401

from lib import hookio


def _edited_path(payload: dict) -> str | None:
    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("path")
    return path


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)
    # Scope to forge-enabled projects, like every other hook. Without this the
    # PostToolUse formatter would run `uv run ruff` on any .py edit in any repo —
    # a silent side effect (and a latency hit while uv resolves an environment)
    # outside the workflow this plugin governs.
    if not os.path.isdir(os.path.join(project, ".forge")):
        return

    path = _edited_path(payload)
    if not path or not path.endswith(".py") or not os.path.exists(path):
        return

    runner = ["uv", "run"] if shutil.which("uv") else []
    if not runner and shutil.which("ruff") is None:
        return  # ruff genuinely unavailable; nothing to do

    for args in (["ruff", "format", path], ["ruff", "check", "--fix", path]):
        try:
            subprocess.run(runner + args, cwd=project, capture_output=True, timeout=60)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # best-effort; never block the edit


if __name__ == "__main__":
    main()
