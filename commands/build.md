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

This command is **resumable**: it only ever works *unchecked* items, so re-running
it after an interruption (or a failed gate) picks up at the first incomplete item
and never re-implements one already ticked off.

For each unchecked item, in order:

1. **Tests first, from the spec.** Write tests against what the plan says the
   behaviour should be — not against the implementation you're about to write
   (that only tests that the code does what it does). For non-trivial test design,
   delegate to the `python-test-author` agent.
2. **Implement** the smallest code that satisfies the item and its tests. Match
   the surrounding code's style, naming, and comment density. Comment the *why*.
   Need a new dependency? Add it with `uv add <pkg>` (dev: `uv add --group dev
   <pkg>`) — never pip, a `requirements.txt`, or a hand-edited pyproject; the
   require_uv hook enforces this.
3. **Keep docs honest in the same step:** if behaviour, config, CLI, or public
   API changed, update `docs/` and `.env.example` now — not later.
4. **Run `/forge:check`.** Fix until green. Only then tick the checklist item.

## Capturing decisions

If the user states a durable directive mid-build, offer `/forge:decide` to record
it (draft + confirm) so it isn't lost.

## Documentation coverage (opt-out)

When the plan is fully checked off and `/forge:check` is green, run `/forge:docs`
on the source root to fill any documentation gaps the new code introduced.

Skip this step when **either** condition holds (they are independent):
- `$ARGUMENTS` contains `--no-docs` — an explicit opt-out the user passed. Skip
  even if production code changed; they've taken responsibility for docs.
- the change touched only tests, docs, config, or tooling — no production source
  changed, so there's nothing new to document. Skip automatically; no flag needed.

If `/forge:docs` edits any files, re-run `/forge:check` to confirm the gate is
still green before summarising.

## Wrap-up

Summarise what changed and remind the user to `/forge:review` and `/forge:audit`
before committing/releasing.

Then output a **"Try it yourself"** section: a concrete, ordered list of steps the
user can run to experience and verify the changes by hand. This is manual
acceptance testing, distinct from the automated suite — it tells the user what to
*do* to see the new behaviour for themselves.

- Cover each user-visible change with at least one step. Skip changes that have no
  user-observable surface (pure refactors, internal helpers); if nothing is
  user-observable, say so in one line instead of inventing steps.
- Make every step actionable and copy-pasteable: the exact command, URL, input,
  or UI action — and the result to expect ("you should see …"). Don't restate the
  automated tests; describe the lived experience.
- Note any setup a step needs (env var, fixture, running server, login) before it.
