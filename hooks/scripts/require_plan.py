"""PreToolUse hook: refuse to edit source without an active plan.

Enforces the first phase boundary: implementation work flows from a written plan,
not from an unscoped impulse. Scoped narrowly so it gates real feature code and
stays out of the way otherwise:

  * only fires on Edit/Write of .py files under src/ (the blessed layout)
  * only in forge-enabled projects (a .forge/ dir is present)
  * honoured override: .forge/override-plan  (one-shot, logged)

An "active plan" = a recorded plan in state, or any checklist under docs/plans/.
"""

import os

import _bootstrap  # noqa: F401

from lib import hookio, state


def _is_source_py(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    norm = path.replace("\\", "/")
    return norm.startswith("src/") or "/src/" in norm


def _has_active_plan(project: str) -> bool:
    if state.load(project).get("active_plan"):
        return True
    plans = os.path.join(project, "docs", "plans")
    try:
        return any(n.endswith(".md") for n in os.listdir(plans))
    except OSError:
        return False


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)
    if not os.path.isdir(os.path.join(project, ".forge")):
        hookio.allow()

    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("path") or ""
    if not _is_source_py(path):
        hookio.allow()

    if state.take_override(project, "plan"):
        hookio.allow()

    if _has_active_plan(project):
        hookio.allow()

    hookio.deny(
        "No active plan for this project. Source edits should follow a plan.\n"
        "Run /forge:plan to spec the change first, or — for a genuinely trivial "
        'fix — run /forge:override plan "<why>" (the bypass is logged) and retry.'
    )


if __name__ == "__main__":
    main()
