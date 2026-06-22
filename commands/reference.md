---
description: Install, list, or author scoped style references for this repo
argument-hint: "[list | add <name> | create <name> | check]"
allowed-tools: Bash, Read, Write, Edit, Agent, AskUserQuestion
---

Manage **style references** — scoped convention guides (e.g. `django`, `cli`,
`python-base`) that govern a subset of files and are checked for drift. References
live committed in `.forge/references/*.md` so they bind the whole repo.

Dispatch on `$ARGUMENTS`:

## `list` (default)

Show what's available and what's installed:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/refs.py" available
python3 "$CLAUDE_PLUGIN_ROOT/bin/refs.py" installed
```

## `add <name>`

Install a library reference into this project:
1. Confirm `$CLAUDE_PLUGIN_ROOT/references/<name>.md` exists (else show `available`).
2. Copy it to `.forge/references/<name>.md` (create the dir if needed).
3. **Tune the scope to this repo.** Read its `applies_to` globs and adjust them to
   the project's actual layout (e.g. point Django globs at the real app paths).
   Confirm the final globs with the user.
4. Report it's installed and now governs the matching files (injected on edit,
   enforced at review).

## `create <name>`

Author a new reference with the user:
1. Ask what kind of code it governs and gather the conventions (keep each rule a
   concrete, checkable imperative — vague rules can't catch drift).
2. Write `.forge/references/<name>.md` with frontmatter (`name`, `summary`,
   `applies_to` globs scoped to this repo, `enforcement: blocking|advisory`) and
   the rules as the body.
3. Confirm the scope with the user.

## `check`

Run a drift pass now: dispatch the **`reference-auditor`** agent over the changed
(or all) files and report violations grouped by enforcement level. Fix blocking
ones or record an explicit override.

Keep references concrete and scoped — a reference that's too broad or too vague
creates noise instead of catching real drift.
