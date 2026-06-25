"""PostToolUse hook: invalidate stale green-gate results when files change.

A recorded "check passed" / "audit passed" is only meaningful against the tree it
was measured on. The moment a relevant file changes, that pass is stale and must
not wave a commit/release through. We drop the relevant record here so the
PreToolUse gates re-demand a fresh run.

  * any .py change      → invalidates `check`, `audit`, and `review` (all of which
                          read code), and joins the dirty set the Stop gate scopes
                          mypy to
  * docs/.env/pyproject → invalidates `audit`
"""

import os

import _bootstrap  # noqa: F401

from lib import hookio, state

_AUDIT_TRIGGERS = (".md", ".rst", ".env.example", "pyproject.toml", "uv.lock")


def _edited_path(payload: dict) -> str | None:
    ti = payload.get("tool_input") or {}
    return ti.get("file_path") or ti.get("path")


def _rel_in_project(project: str, path: str) -> str | None:
    """`path` relative to the project root, or None if it falls outside it.

    Claude passes absolute file paths; we normalise to a project-relative path so
    the dirty set stays portable and never points outside the tree mypy runs on."""
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(project))
    return None if rel.startswith("..") else rel


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)
    # Only forge-enabled projects carry state worth invalidating.
    if not os.path.isdir(os.path.join(project, ".forge")):
        return

    path = _edited_path(payload)
    if not path:
        return
    base = os.path.basename(path)

    if path.endswith(".py"):
        state.invalidate(project, "check")
        state.invalidate(project, "audit")
        state.invalidate(project, "review")
        rel = _rel_in_project(project, path)
        if rel:
            state.add_dirty(project, rel)
    elif base.endswith(_AUDIT_TRIGGERS):  # includes .env.example
        state.invalidate(project, "audit")


if __name__ == "__main__":
    main()
