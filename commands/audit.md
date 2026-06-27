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
completeness, **version agreement** (every place the project records its version —
`pyproject.toml`, package `__version__`, `.claude-plugin/` manifests — must
match), metadata agreement, and **security**: known-vulnerable dependencies
(`pip-audit`) and risky code patterns (`bandit`). Fix every `✗` (warnings `!` are
advisory — address or consciously accept). Re-run until clean.

The security scanners are optional: if `pip-audit`/`bandit` aren't installed the
check is *skipped with a hint*, not failed — add them with `uv add --group dev
pip-audit bandit` to turn it on. Dependency CVEs are blocking; code findings are
advisory by default (set `FORGE_SECURITY_STRICT=1` to make HIGH-severity/
HIGH-confidence ones block). Deep, logic-level security review is the `python-security-auditor` agent's
job in `/forge:review`.

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
