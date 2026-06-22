---
description: Capture a durable project decision as a binding directive + ADR
argument-hint: "[the decision]"
allowed-tools: Bash, Read, AskUserQuestion
---

Record a durable design decision so it binds all future work. `$ARGUMENTS` (or the
directive you detected mid-conversation) is the starting point.

This exists because intent stated in chat evaporates. Once recorded, the directive
is injected into every session and enforced by `/forge:review`.

## Draft, then confirm (never record silently)

1. Shape the decision into:
   - **title** — short noun phrase
   - **context** — the forces/problem that make it necessary (facts, not the rule)
   - **decision** — what is decided
   - **rationale** — why this over the alternatives; the trade-off
   - **directive** — ONE terse imperative for `.forge/directives.md` (e.g.
     "CLI MUST use subcommands, never a flag-driven monolith")
2. **Show the draft to the user and get explicit confirmation.** Auto-capture is
   fine; silent recording is not. Refine wording if they push back. If it
   contradicts an existing directive, surface that and ask whether this supersedes
   it (note the superseded ADR in the new one's context).

## Record it

Pipe the confirmed draft as JSON (include today's date `YYYY-MM-DD`) to:

```bash
echo '<json>' | python3 "$CLAUDE_PLUGIN_ROOT/bin/decide.py"
```

Fields: `title, context, decision, rationale, directive, date`. The script
allocates the ADR number, writes `docs/decisions/NNNN-*.md`, appends the directive
to `.forge/directives.md`, and updates the decision index.

Confirm to the user what was recorded and where, and note it now binds all future
sessions.
