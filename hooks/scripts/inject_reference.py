"""PreToolUse hook: inject governing style references before editing a file.

When you're about to edit a file a reference governs (by its applies_to globs),
this surfaces that reference's rules into context — so you write to the convention
instead of drifting from it. Injected at most once per reference per session
(tracked in state) to avoid re-spending tokens on every edit.

Never blocks: it only adds context. Enforcement of violations is the
reference-auditor's job at review time.
"""

import os

import _bootstrap  # noqa: F401

from lib import hookio, references


def _edited_path(payload: dict) -> str | None:
    ti = payload.get("tool_input") or {}
    return ti.get("file_path") or ti.get("path")


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)
    if not os.path.isdir(os.path.join(project, ".forge")):
        return
    session = payload.get("session_id") or "default"

    path = _edited_path(payload)
    if not path:
        return
    rel = os.path.relpath(path, project)

    blocks = []
    for ref in references.for_file(project, rel):
        if references.was_injected(project, session, ref.name):
            continue
        blocks.append(references.injection_block(ref))
        references.mark_injected(project, session, ref.name)

    if blocks:
        hookio.inject_context("PreToolUse", "\n\n".join(blocks))


if __name__ == "__main__":
    main()
