#!/usr/bin/env python3
"""CLI entrypoint for /forge:plan — record which plan is active.

Usage:  plan active <path>

Sets the `active_plan` field in .forge/state.json so the command doesn't have to
hand-edit the JSON (the one state mutation that previously had no helper; a
malformed write there corrupts workflow state). `<path>` is the plan file the
command just wrote, e.g. `docs/plans/0003-thing.md`.

Exit status: 0 = recorded, 2 = bad usage.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import state  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "active":
        print("usage: plan.py active <path>", file=sys.stderr)
        return 2
    state.set_active_plan(os.getcwd(), argv[1])
    print(f"Active plan set to {argv[1]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
