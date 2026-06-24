#!/usr/bin/env python3
"""CLI entrypoint for /forge:override — arm a one-shot, logged gate bypass.

Usage:  override <gate> [reason...]

`gate` is one of the gates that accept a sentinel (state.OVERRIDE_GATES). The
bypass is *armed*, not applied: the next matching gated action consumes it and
records the bypass in the override trail. This is the ergonomic front door to the
mechanism the hooks already honour (writing .forge/override-<gate> by hand still
works) — so a real hotfix is never held hostage, but the skip is always logged.

Exit status: 0 = armed, 2 = bad usage.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import state  # noqa: E402


def main(argv: list[str]) -> int:
    gate = argv[0] if argv else ""
    if gate not in state.OVERRIDE_GATES:
        print(
            f"usage: override <{'|'.join(state.OVERRIDE_GATES)}> [reason]",
            file=sys.stderr,
        )
        return 2

    reason = " ".join(argv[1:]).strip()
    state.request_override(os.getcwd(), gate, reason)

    print(f"Armed a one-shot override for the '{gate}' gate.")
    print(f"Reason: {reason}" if reason else "Reason: (none given — recommend one)")
    print(
        "The next matching gated action will be allowed exactly once, and the "
        "bypass recorded in .forge/state.json."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
