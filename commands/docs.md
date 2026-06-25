---
description: Crawl the codebase, find features with missing or thin project documentation, and write or expand the relevant markdown
argument-hint: "[--no-write to report only]"
allowed-tools: Bash, Read, Write, Edit, Agent
---

Improve markdown documentation coverage across `docs/` and `README.md`.

## Phase 1 — Gap scan

Dispatch the **`doc-gap-scanner`** agent on the project root. It returns a JSON
object with a `gaps` array: every command, agent, script, public symbol, template,
or config key that either has no doc coverage (`MISSING`) or only a passing
mention (`THIN`).

If `gaps` is empty, report "Documentation coverage looks complete." and stop.

If `$ARGUMENTS` contains `--no-write`, print the gap list as a markdown table and
stop — don't edit any files.

## Phase 2 — Write

Process gaps in this priority order: `MISSING` before `THIN`, higher-level
abstractions (commands, agents) before implementation details (symbols, env vars).

For each gap:

1. **Read the source.** Read the relevant source file fully — the command/agent
   markdown, the Python script, or the module. Understand what it does, its
   inputs/outputs, when to use it, and any notable behaviour or caveats.

2. **Decide where the doc goes:**
   - If a `docs/` file already covers the same topic area, expand that file.
   - If the gap is a primary user-facing feature (command, agent) with no
     existing home, create `docs/<kind>/<name>.md`.
   - Minor items (env vars, internal scripts) go into `docs/reference.md` (create
     if it doesn't exist) as a new section.
   - README.md: only add here if the gap is something a new user hits in the
     first five minutes (install, quickstart, the core workflow).

3. **Write the documentation.** Produce clear, direct prose aimed at a developer
   who is new to this project. For each item, cover:
   - What it is and when to reach for it
   - How to invoke it / what it expects
   - A concrete example if the usage isn't obvious
   - Any caveats, preconditions, or interactions with other parts of the workflow

   For `THIN` gaps: read the existing section (note `mentioned_in` and
   `mentioned_line` from the gap record), then expand it in place — don't
   duplicate, extend.

4. **Edit the file.** Insert at a logical position (after a related section,
   before the next same-level section). Use the heading level that fits the
   surrounding structure.

## Report

After writing:

```
Documentation pass complete
  Gaps found:    N (X MISSING, Y THIN)
  Documented:    M  (list: name → file)
  Skipped:       K  (list: name — reason)
```

Remind the user to review the diff (`git diff docs/ README.md`) before running
`/forge:audit`, since the doc-sync auditor will now verify these new claims
against the code.
