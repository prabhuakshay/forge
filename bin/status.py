#!/usr/bin/env python3
"""CLI entrypoint for /forge:status — print a snapshot of workflow state.

A thin wrapper: all the formatting lives in lib/status.report so it can be
unit-tested in-process. Always exits 0 — status is a read, never a gate.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import status  # noqa: E402


def main() -> int:
    print(status.report(os.getcwd()), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
