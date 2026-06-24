"""PreToolUse hook: refuse dependency commands that aren't `uv`.

Forge mandates a single dependency manager. Dependencies are added with
`uv add` (recorded in pyproject.toml + uv.lock) and removed with `uv remove` —
never pip, a requirements file, `uv pip install`, or a hand-edited pyproject.
This gate blocks the alternatives so the lockfile stays the source of truth.

  * fires on Bash commands that install/modify deps with a non-uv tool
    (pip, uv pip, poetry, pipenv, conda, pip-tools, easy_install)
  * only in forge-enabled projects
  * override: .forge/override-uv (one-shot, logged) — the audited escape hatch
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
    offender = cmdscan.dep_install_command(command)
    if not offender:
        hookio.allow()

    if state.take_override(project, "uv"):
        hookio.allow()

    hookio.deny(
        f"`{offender}` is blocked — forge manages dependencies with uv only.\n"
        "Add deps with `uv add <pkg>` (dev deps: `uv add --group dev <pkg>`), "
        "remove with `uv remove <pkg>`. uv records the change in pyproject.toml "
        "and uv.lock for you — never use pip, requirements files, `uv pip "
        "install`, or hand-edit the pyproject dependency lists.\n"
        "To bypass for a deliberate reason, create .forge/override-uv with a "
        "one-line justification (it will be logged) and retry."
    )


if __name__ == "__main__":
    main()
