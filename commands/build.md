---
description: Implement an active plan item-by-item, tests alongside, gate green
argument-hint: "[plan file or item, optional]"
allowed-tools: Bash, Read, Write, Edit, Agent, AskUserQuestion
---

Implement the active plan. `$ARGUMENTS` may name a specific plan or item;
otherwise use the `active_plan` in `.forge/state.json`, or the newest file in
`docs/plans/`.

## Before writing code

Read `.forge/directives.md` and the plan. **You are bound by every directive** —
treat a violation as a defect, not a trade-off. If no plan exists, stop and tell
the user to run `/forge:plan` (the require_plan hook will block source edits anyway).

## Work the checklist

For each unchecked item, in order:

1. **Tests first, from the spec.** Write tests against what the plan says the
   behaviour should be — not against the implementation you're about to write
   (that only tests that the code does what it does). For non-trivial test design,
   delegate to the `python-test-author` agent.
2. **Implement** the smallest code that satisfies the item and its tests. Match
   the surrounding code's style, naming, and comment density. Comment the *why*.
3. **Keep docs honest in the same step:** if behaviour, config, CLI, or public
   API changed, update `docs/` and `.env.example` now — not later.
4. **Run `/forge:check`.** Fix until green. Only then tick the checklist item.

## Capturing decisions

If the user states a durable directive mid-build, offer `/forge:decide` to record
it (draft + confirm) so it isn't lost.

When the plan is fully checked off, summarise what changed and remind the user to
`/forge:review` and `/forge:audit` before committing/releasing.
