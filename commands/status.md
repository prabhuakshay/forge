---
description: Show a snapshot of forge workflow state — gates, dirty files, references, overrides
allowed-tools: Bash
---

Show where this project stands in the forge workflow. Run:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/status.py"
```

This reads `.forge/state.json` (and the installed references and directives) and
prints, in one screen:

- the current **phase** and **active plan**;
- each **gate** — `check` (commit), `review` (commit; shown only when the project
  has binding directives or a governing reference), and `audit` (push/publish) —
  as green for the current tree, **stale** (code changed since it last passed), or
  never run;
- the **dirty set**: source files edited since the last green check;
- installed **style references** and their scope;
- the count of binding **directives**;
- any **armed override** (a one-shot bypass about to fire) and recent override
  **history**.

Print the output verbatim, then, if anything is red or stale, name the single
next command that moves it forward (e.g. "run /forge:check"). Don't take any
other action — this command only reports.
