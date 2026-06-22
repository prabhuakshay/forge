---
description: Run the code quality gate (ruff, mypy, pytest+cov) and fix failures
allowed-tools: Bash, Read, Edit
---

Run the **code** gate and drive it to green. This is the gate that unblocks
committing.

1. Run it:

   ```bash
   python3 "$CLAUDE_PLUGIN_ROOT/bin/check.py"
   ```

   This runs `ruff format --check`, `ruff check`, `mypy`, and `pytest` with the
   project's coverage floor, prints a summary, and — on green — records the pass
   against the current source fingerprint so `git commit` is unblocked.

2. If it exits non-zero, read the printed tool output, **fix the actual problems**
   (don't suppress lint rules or loosen types to dodge them — the goal is correct
   code, not a quiet checker), and re-run until green.

3. If a step is *skipped* (tool missing), tell the user what to install (likely
   `uv sync --all-extras`) rather than declaring success.

Report the final state plainly: green, or the specific remaining failures. Do not
record a pass by any other means — only `bin/check.py` on a genuinely green run
may do that.
