#!/usr/bin/env python3
"""CLI entrypoint for /forge:override — arm a one-shot, logged gate bypass.

Usage:  override <gate> [reason...]   arm a one-shot bypass of <gate>
        override list                 print the consumed-override trail
        override prune [keep_count]   compact the trail (default: clear all)

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


def _list(project: str) -> int:
    """Print the consumed-override trail, newest last."""
    history = state.load(project).get("overrides") or []
    if not history:
        print("No overrides recorded.")
        return 0
    print(f"Override history ({len(history)}):")
    for entry in history:
        print(
            f"  {entry.get('at', '?')}  {entry.get('gate', '?')} — "
            f"{entry.get('reason', '')}"
        )
    return 0


def _prune(project: str, argv: list[str]) -> int:
    """Compact the trail, keeping the N most recent (default 0 = clear all)."""
    keep = 0
    if argv:
        try:
            keep = int(argv[0])
        except ValueError:
            print("usage: override prune [keep_count]", file=sys.stderr)
            return 2
    removed = state.prune_overrides(project, keep)
    print(f"Pruned {removed} override record(s); kept the {keep} most recent.")
    return 0


def main(argv: list[str]) -> int:
    project = os.getcwd()
    sub = argv[0] if argv else ""
    if sub == "list":
        return _list(project)
    if sub == "prune":
        return _prune(project, argv[1:])

    gate = sub
    if gate not in state.OVERRIDE_GATES:
        print(
            f"usage: override <{'|'.join(state.OVERRIDE_GATES)}> [reason]\n"
            "       override list\n"
            "       override prune [keep_count]",
            file=sys.stderr,
        )
        return 2

    reason = " ".join(argv[1:]).strip()
    state.request_override(project, gate, reason)

    print(f"Armed a one-shot override for the '{gate}' gate.")
    print(f"Reason: {reason}" if reason else "Reason: (none given — recommend one)")
    print(
        "The next matching gated action will be allowed exactly once, and the "
        "bypass recorded in .forge/state.json."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
