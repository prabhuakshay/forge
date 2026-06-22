#!/usr/bin/env python3
"""Atomically record a decision: write the ADR, append the directive, update the index.

Reads a JSON draft on stdin so the command can confirm wording with the user before
anything is written:

  {"title": "...", "context": "...", "decision": "...",
   "rationale": "...", "directive": "...", "date": "YYYY-MM-DD"}

ADR numbering is allocated here (not by the agent) so concurrent or repeated calls
can't collide on a number. Prints the paths it touched.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import decisions  # noqa: E402


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid JSON draft: {exc}", file=sys.stderr)
        return 1

    required = ("title", "context", "decision", "rationale", "directive", "date")
    missing = [k for k in required if not data.get(k)]
    if missing:
        print(f"Draft missing fields: {', '.join(missing)}", file=sys.stderr)
        return 1

    project = os.getcwd()
    number = decisions.next_adr_number(project)
    draft = decisions.AdrDraft(
        number=number,
        title=data["title"],
        context=data["context"],
        decision=data["decision"],
        rationale=data["rationale"],
        directive=data["directive"],
    )

    # 1) Write the ADR.
    ddir = decisions.decisions_dir(project)
    os.makedirs(ddir, exist_ok=True)
    adr_name = decisions.adr_filename(number, draft.title)
    adr_path = os.path.join(ddir, adr_name)
    with open(adr_path, "w", encoding="utf-8") as fh:
        fh.write(decisions.render_adr(draft, data["date"]))

    # 2) Append the binding directive (creating the file if needed).
    dpath = decisions.directives_path(project)
    os.makedirs(os.path.dirname(dpath), exist_ok=True)
    with open(dpath, "a", encoding="utf-8") as fh:
        fh.write(decisions.directive_line(draft) + "\n")

    # 3) Append to the decision index if present.
    index = os.path.join(ddir, "README.md")
    if os.path.exists(index):
        with open(index, "a", encoding="utf-8") as fh:
            fh.write(f"- [{number:04d}. {draft.title}]({adr_name}) — Accepted\n")

    print(f"Recorded decision {number:04d}.")
    print(f"  ADR:       {os.path.relpath(adr_path, project)}")
    print(f"  Directive: {os.path.relpath(dpath, project)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
