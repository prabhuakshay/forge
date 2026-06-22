#!/usr/bin/env python3
"""Emit verifiable doc claims as JSON for the doc-sync auditor agent.

The agent consumes this list and checks each claim against the code. Pre-filtering
here (cheap, mechanical) is what keeps the agent fast and grounded: it reasons only
about concrete, located claims instead of re-reading every doc from scratch.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import doc_claims  # noqa: E402


def main() -> int:
    claims = doc_claims.extract(os.getcwd())
    print(json.dumps(claims, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
