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
    # Allocation + the three writes happen together under the .forge lock, so
    # concurrent /forge:decide runs can't collide on a number (see record_decision).
    number, adr_path, dpath = decisions.record_decision(
        project,
        title=data["title"],
        context=data["context"],
        decision=data["decision"],
        rationale=data["rationale"],
        directive=data["directive"],
        date=data["date"],
    )

    print(f"Recorded decision {number:04d}.")
    print(f"  ADR:       {os.path.relpath(adr_path, project)}")
    print(f"  Directive: {os.path.relpath(dpath, project)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
