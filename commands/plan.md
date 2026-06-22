---
description: Spec a change into an atomic, reviewable plan checklist
argument-hint: "[what you want to build]"
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

Turn the request in `$ARGUMENTS` into a written plan **before** any code. A good
plan is where ambiguity dies — resolve it here, not mid-implementation.

## First, load the rules

Read `.forge/directives.md` (if present). The plan must comply with every binding
directive. If the request seems to require violating one, stop and say so — offer
`/forge:decide` to change the directive rather than quietly diverging.

## Produce the plan

1. **Clarify** anything underspecified about behaviour, scope, or edge cases —
   ask with AskUserQuestion rather than assuming. Restate the goal in one sentence.
2. **Design briefly:** the approach, the modules/functions touched, the data
   shapes, and explicitly what is *out* of scope.
3. **Write `docs/plans/NNNN-<slug>.md`** (next free number) as an **atomic
   checklist** — each item independently implementable and verifiable, with a
   `## Verification` section stating how each will be tested.
4. Record the plan as active: append its path to `.forge/state.json`'s
   `active_plan` field (read-modify-write the JSON; create `.forge` if missing).

## Watch for durable decisions

If, while planning, the user states a **durable design directive** ("it must
always work this way", "never do X", "the CLI should be shaped like this"), pause
and offer to capture it with `/forge:decide` — draft the wording and confirm
before recording. This is how intent survives beyond this conversation.

Output the plan path and a short summary. Do not start implementing — that's
`/forge:build`.
