---
description: Verify everything around the code is in sync — docs, .env, deps, metadata
allowed-tools: Bash, Read, Edit, Agent
---

Run the **non-code** gate: is everything *around* the code honest and in sync?
This is what unblocks push/publish. Audit is green only when **both** halves below
pass.

## 1. Mechanical checks

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/audit.py"
```

This checks `.env.example` ↔ code config, `uv.lock` sync, scaffolding
completeness, and metadata agreement. Fix every `✗` (warnings `!` are advisory —
address or consciously accept). Re-run until clean.

## 2. Doc ↔ code sync (the no-excuse part)

Get the verifiable doc claims:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/doc_claims.py"
```

Hand them to the **`doc-sync-auditor`** agent and have it verify each claim
against the code. For every `MISMATCH`/`MISSING` it returns **with code
evidence**, fix the documentation (or the code, if the docs describe the intended
contract and the code regressed). Ignore any finding the agent could not ground
in a `file:line` — those are not actionable.

Repeat until the auditor reports the docs in sync.

## 3. Record the pass

Only when (1) is clean **and** (2) reports synced:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/mark.py" audit
```

Report what was fixed and confirm the audit is green (push/publish unblocked).
Never run `mark.py audit` while anything above is unresolved.
