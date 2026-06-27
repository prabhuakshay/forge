---
description: Quality + correctness + directive-compliance review of the changes
allowed-tools: Bash, Read, Edit, Agent
---

Review the current changes before they're committed. Scope to what actually
changed (use `git diff` / `git status`) unless asked for a whole-codebase pass.

## Load the rules first

Read `.forge/directives.md`. **A directive violation is a blocking finding** —
the strongest category in this review.

## Run the reviewers

Dispatch in parallel and collect findings:

- **`python-quality-auditor`** — readability, maintainability, naming, structure,
  comment honesty on the changed code.
- **`reference-auditor`** — checks changed files against the style references that
  govern them (`.forge/references/`). Blocking-reference violations are blocking
  findings.
- **`python-security-auditor`** — logic-level security review of changed code that
  crosses a trust boundary (input, I/O, subprocess, deserialization, secrets,
  auth). Complements the mechanical `pip-audit`/`bandit` scans the audit gate
  runs. Skip when the change has no security-relevant surface.
- For Django projects, also use the project's `django-quality-auditor` and
  `django-security-auditor` agents on the changed code.
- Yourself: check correctness, edge cases, and that each change honours the
  binding directives and the plan it came from.

## Report

Group findings as **Blocking** (directive violations, correctness bugs, security)
vs **Suggested** (quality, simplification). For blocking items, fix them or, with
the user's agreement, record an explicit override. Don't mark the review done
while a blocking finding stands unaddressed.

## Record the pass

Once **zero blocking findings remain** for the current tree, record the review so
the commit gate recognises it:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/mark.py" review
```

This matters for projects with binding directives or governing references: the
`require_review` hook blocks `git commit` until review is green for the current
tree (any later `.py` edit re-arms it). Record the pass **only** when the review
genuinely came back clean — never to quiet the gate. If a blocking finding is being
deliberately shipped, use `/forge:override review "<why>"` (logged) instead.

End by reminding the user to `/forge:check` and `/forge:audit` if not already
green.
