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
import re

import _bootstrap  # noqa: F401

from lib import hookio, state

# An unchecked Markdown checklist item: `- [ ]` / `* [ ]` (any indent). A plan
# whose items are all ticked off is *complete*, not active — see _has_active_plan.
_OPEN_ITEM = re.compile(r"(?m)^\s*[-*]\s+\[ \]")


def _is_source_py(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    norm = path.replace("\\", "/")
    return norm.startswith("src/") or "/src/" in norm


def _has_open_items(path: str) -> bool:
    """True if `path` is a readable plan with at least one unchecked item."""
    try:
        with open(path, encoding="utf-8") as fh:
            return bool(_OPEN_ITEM.search(fh.read()))
    except OSError:
        return False


def _has_active_plan(project: str) -> bool:
    """An active plan is one with work left to do — at least one unchecked
    checklist item. A completed plan (every item ticked) or an empty file no
    longer holds the gate open, so finishing a plan correctly re-demands a new
    one before more source is written. We check the recorded `active_plan` first,
    then any checklist under docs/plans/."""
    candidates: list[str] = []
    active = state.load(project).get("active_plan")
    if isinstance(active, str) and active:
        candidates.append(
            active if os.path.isabs(active) else os.path.join(project, active)
        )
    plans = os.path.join(project, "docs", "plans")
    try:
        candidates += [
            os.path.join(plans, n)
            for n in sorted(os.listdir(plans))
            if n.endswith(".md")
        ]
    except OSError:
        pass
    return any(_has_open_items(p) for p in candidates)


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)
    if not os.path.isdir(os.path.join(project, ".forge")):
        hookio.allow()

    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("path") or ""
    if not _is_source_py(path):
        hookio.allow()

    # Active plan before override: if one exists there's nothing to bypass, so
    # don't consume (and log) a one-shot override needlessly. See require_check.
    if _has_active_plan(project):
        hookio.allow()

    if state.take_override(project, "plan"):
        hookio.allow()

    hookio.deny(
        "No active plan for this project. Source edits should follow a plan.\n"
        "Run /forge:plan to spec the change first, or — for a genuinely trivial "
        'fix — run /forge:override plan "<why>" (the bypass is logged) and retry.'
    )


if __name__ == "__main__":
    main()
