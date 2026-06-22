#!/usr/bin/env python3
"""Record a gate pass against the current source fingerprint.

Used by commands whose gate has both mechanical and agent-judged parts (audit):
the command calls this only once *everything* is confirmed green, so the pass is
honest. Usage: `python3 bin/mark.py <check|audit>`.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import state  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"check", "audit"}:
        print("usage: mark.py <check|audit>", file=sys.stderr)
        return 2
    state.record_pass(os.getcwd(), sys.argv[1])
    print(f"Recorded {sys.argv[1]} pass for the current tree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
