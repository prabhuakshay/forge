"""PreToolUse hook: refuse `git commit` unless the code gate is currently green.

You cannot commit on top of unproven code. A commit is allowed only if /forge:check
passed AND nothing has changed since (tracked via the source fingerprint). Editing
any .py invalidates that pass via mark_dirty.py, so "passed earlier" never counts.

  * fires on Bash commands that invoke `git commit`
  * only in forge-enabled projects
  * override: .forge/override-check (one-shot, logged) — the audited escape hatch
"""

import os

import _bootstrap  # noqa: F401

from lib import cmdscan, hookio, state


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)
    if not os.path.isdir(os.path.join(project, ".forge")):
        hookio.allow()

    ti = payload.get("tool_input") or {}
    command = ti.get("command") or ""
    # Detect a real `git commit` invocation — not a commit message or other
    # argument that merely contains the words (see lib/cmdscan).
    if not cmdscan.runs_git_subcommand(command, "commit"):
        hookio.allow()

    if state.take_override(project, "check"):
        hookio.allow()

    if state.is_current(project, "check"):
        hookio.allow()

    hookio.deny(
        "Code gate is not green for the current tree. Commit blocked.\n"
        "Run /forge:check and fix any failures (ruff, mypy, pytest), then commit.\n"
        "To bypass for a deliberate reason, run /forge:override check "
        '"<why>" (the bypass is logged) and retry.'
    )


if __name__ == "__main__":
    main()
