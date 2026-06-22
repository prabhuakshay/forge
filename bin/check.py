#!/usr/bin/env python3
"""CLI entrypoint for /forge:check — run the code gate, record a pass if green.

Invoked by the command as `python3 "$CLAUDE_PLUGIN_ROOT/bin/check.py"`. Prints a
readable summary plus the raw tool output for any failures (so the agent can fix
them), and records the green result against the current source fingerprint so the
commit gate will let a commit through. Exit status: 0 = green, 1 = failures.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import gate, state  # noqa: E402


def main() -> int:
    project = os.getcwd()
    result = gate.run_full(project)

    print("forge check\n" + result.summary())
    for step in result.failures():
        print(f"\n--- {step.name} failed ---\n{step.output}")

    if result.ok:
        state.record_pass(project, "check")
        print("\nGREEN — code gate passed; commit is unblocked.")
        return 0
    print("\nRED — fix the failures above and re-run /forge:check.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
