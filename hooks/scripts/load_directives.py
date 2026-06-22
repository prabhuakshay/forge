"""SessionStart hook: inject the project's binding directives and reference index.

This is the mechanical core of "never ignored". Every session — for any agent,
on any task — begins with the agreed constraints already in context, so obeying
them isn't contingent on someone remembering to open a file. We also inject a
compact index of installed style references (name → what it governs) so the agent
knows which guides exist before it touches a governed file.
"""

import _bootstrap  # noqa: F401  (sys.path side effect)

from lib import decisions, hookio, references


def main() -> None:
    payload = hookio.read_input()
    project = hookio.project_dir(payload)
    parts = [
        decisions.injection_block(project),
        references.index_block(project),
    ]
    block = "\n\n".join(p for p in parts if p)
    if block:
        hookio.inject_context("SessionStart", block)
    # Nothing recorded yet — inject nothing rather than noise.


if __name__ == "__main__":
    main()
