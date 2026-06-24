# `.forge/state.json` schema

forge keeps a small amount of per-project workflow state in
`<project>/.forge/state.json`. It is a plain, git-untracked JSON file (so it
survives across sessions and is trivial to inspect or reset by hand) written and
read by `lib/state.py` and `lib/references.py`. This document is the reference
for its keys; the authoritative behaviour lives in those modules.

A freshly created file (see `state.load`) has this skeleton:

```json
{
  "phase": null,
  "active_plan": null,
  "last_check": null,
  "last_audit": null,
  "dirty_py": [],
  "overrides": []
}
```

A missing or corrupt file is treated as this empty skeleton, so no caller has to
special-case "no state yet".

## Keys

| Key | Type | Meaning |
|---|---|---|
| `phase` | string \| null | The workflow phase the project is in. Advisory; set by commands. |
| `active_plan` | string \| null | Path to the plan `/forge:build` is currently working, relative to the project root. |
| `last_check` | object \| null | The last green **code gate** result (see *Gate records* below), or null if none/stale. |
| `last_audit` | object \| null | The last green **audit** result, same shape as `last_check`. |
| `dirty_py` | string[] | Source files edited since the last green check — the Stop gate type-checks only these. Cleared when a full check passes. |
| `overrides` | object[] | Append-only audit trail of deliberate gate bypasses (see *Overrides* below). |
| `ref_injection` | object | Per-session bookkeeping for style-reference injection (see *Reference injection* below). Written by `lib/references.py`. |

### Gate records (`last_check`, `last_audit`)

Each is an object recorded by `state.record_pass` when a gate passes:

```json
{
  "passed": true,
  "fingerprint": "<sha256 of the first-party Python source tree>",
  "at": "2026-06-24T12:00:00+00:00"
}
```

- `fingerprint` is the content-addressed `code_fingerprint` of the source tree
  (each first-party `.py` file's relative path plus a sha256 of its bytes;
  vendor/venv/cache dirs are pruned). A gate is "still green" only if this
  fingerprint matches the tree as it is now (`state.is_current`) — so any
  byte-level source change invalidates it, while a no-op like a branch switch
  that leaves bytes unchanged does not.
- `at` is a UTC ISO-8601 timestamp (`now_iso`, seconds precision).

A green `check` clears `dirty_py`, because a passing full gate proves the whole
tree and leaves nothing outstanding for the incremental Stop gate.

### Overrides (`overrides`)

Every entry records that a human deliberately bypassed a gate. Entries are
**kept, not consumed** — the trail of what was skipped and why is the point:

```json
{ "gate": "check", "reason": "urgent hotfix", "at": "2026-06-24T12:00:00+00:00" }
```

A one-shot override is requested with `/forge:override <gate> "<reason>"`, which
writes the sentinel file `<project>/.forge/override-<gate>` (its contents become
the `reason`); writing that file by hand does the same thing.
`state.take_override` reads and **deletes** the sentinel on use, then appends an
entry here — so a bypass applies to exactly one gated action and is always
logged. Gates: `check`, `audit`, `stop`, `plan`, `uv` (`state.OVERRIDE_GATES`).

The sentinel files are the *armed* overrides — what `state.pending_overrides`
returns and `/forge:status` surfaces *before* they fire — as distinct from this
`overrides` trail, which is what has *already* fired and been logged.

### Reference injection (`ref_injection`)

Tracks which style references have already been injected into the current
session, so a reference is injected at most once per session rather than on every
edit:

```json
{ "session": "<session id>", "names": ["django", "cli"] }
```

When the session id changes, the record resets, so it never grows without bound.

## Resetting

Deleting `.forge/state.json` (or the whole `.forge/` directory) resets all
workflow state. The next gate run recreates it. Removing only `last_check` /
`last_audit` (set to `null`) forces the corresponding gate to run again.
