---
description: Arm a one-shot, logged bypass of a forge gate (check, audit, review, stop, plan, uv)
argument-hint: "<check|audit|review|stop|plan|uv> <reason>"
allowed-tools: Bash
---

Arm a **one-shot, logged** bypass of a forge gate, for when a deliberate action
is being held by a gate you intend to skip (a real hotfix, a known-irrelevant
failure). The bypass applies to exactly **one** gated action and is recorded in
`.forge/state.json` — it is an audited escape hatch, never a silent one.

The gates:

| Gate | What it blocks | Bypass when… |
|---|---|---|
| `check` | `git commit` on a non-green tree | committing a hotfix you'll fix forward |
| `review` | `git commit` when binding directives/references aren't reviewed green | shipping a change whose review you'll do forward |
| `audit` | `git push` / publish with doc/config drift | shipping urgently, drift tracked separately |
| `stop` | ending the turn on a broken tree | the broken state is a deliberate stopping point |
| `plan` | editing `src/**.py` with no active plan | a genuinely trivial one-off edit |
| `uv` | non-uv dependency commands | a one-off command uv can't express |

**A reason is expected** — it's the whole point of the audit trail. Parse the
gate and reason from `$ARGUMENTS` and run:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/override.py" <gate> "<reason>"
```

Then tell the user the override is armed and which single action it will permit,
and retry that action. Do not arm an override the user didn't ask for: surface
the gate's failure and let them decide. (Writing `.forge/override-<gate>` by hand
does the same thing — this command is just the ergonomic front door.)

## Reviewing and pruning the trail

The consumed-override trail is append-only by design — it's the record of what was
skipped and why. To inspect or compact it:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/override.py" list            # show the trail
python3 "$CLAUDE_PLUGIN_ROOT/bin/override.py" prune [keep]    # keep newest N (default 0 = clear)
```

`/forge:status` nudges toward this when the trail piles up: many bypasses usually
mean a gate is mis-calibrated for the project (worth a `/forge:decide` to adjust)
or the history just needs compacting. Pruning never touches an *armed* (not-yet-
consumed) override — only history.
