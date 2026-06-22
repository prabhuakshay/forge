# forge

[![ci](https://github.com/prabhuakshay/forge/actions/workflows/ci.yml/badge.svg)](https://github.com/prabhuakshay/forge/actions/workflows/ci.yml)

An opinionated **Python project workflow** as a Claude Code plugin. It makes the
quality bar *executable* and makes the agent run it on every loop — so projects
come out consistent, stable, well-documented, and honest about their own state.

## The loop

```
/forge:init  →  /forge:plan  →  /forge:build  →  /forge:check  →  /forge:audit  →  /forge:release
                     ▲                                                                    │
                     └──────────────── /forge:decide (capture durable intent) ◄───────────┘
```

| Command | Phase | Gate it satisfies |
|---|---|---|
| `/forge:init` | Scaffold a project (or retrofit one) with the full toolchain & docs | — |
| `/forge:plan` | Turn a request into an atomic checklist before any code | plan exists |
| `/forge:build` | Implement a plan item-by-item, tests from the spec | — |
| `/forge:check` | Code gate: ruff + mypy + pytest/coverage | **unblocks commit** |
| `/forge:audit` | Non-code sync: docs↔code, `.env`, lockfile, deps, metadata | **unblocks push/publish** |
| `/forge:review` | Quality + correctness + directive/reference compliance | — |
| `/forge:release` | Version bump, changelog, build, publish | — |
| `/forge:decide` | Record a durable directive + ADR | binds all future work |
| `/forge:reference` | Install/author scoped style references (django, cli, …) | catches style drift |

## What makes it stick

**The gates are enforced by hooks, not goodwill:**

- **PostToolUse** auto-formats every `.py` you touch (`ruff format` + safe fixes)
  and invalidates any stale "green" result.
- **PreToolUse** blocks `git commit` unless `/forge:check` is green for the current
  tree, blocks `git push`/publish unless `/forge:audit` is green, and blocks source
  edits with no active plan.
- **Stop** won't let the agent end a turn on a broken tree (lint/types red, or env
  vars read in code but undocumented in `.env.example`).
- **SessionStart** injects the project's binding directives into every session.

Every block has a **logged one-shot override** (`.forge/override-<gate>`) so a real
hotfix is never held hostage — but the bypass is recorded, never silent.

**Durable intent is captured, not lost.** When you tell the agent how something
must be designed, `/forge:decide` writes it as a binding directive
(`.forge/directives.md`) plus a dated ADR (`docs/decisions/`). The directives are
re-injected every session and enforced in review — so no future agent can quietly
ignore a decision you already made.

**Docs can't silently drift.** `/forge:audit` runs the `doc-sync-auditor` agent,
which is grounded by design: it only reports doc↔code drift it can tie to a
`file:line`, so it catches real staleness without hallucinating.

**Style stays consistent via scoped references.** Install convention guides
(`/forge:reference add django`) that govern a subset of files by glob — `django.md`
covers your Django code, `cli.md` your CLI code, `python-base.md` everything. They
work two ways: the relevant reference is **injected into context the moment you
edit a file it governs** (once per session), and the grounded `reference-auditor`
checks changed files against them at review time. A `blocking` reference's rules
are mandatory; `advisory` ones warn. Author your own with
`/forge:reference create`. This is how style drift gets caught the same way doc
and config drift do — references travel with the repo in `.forge/references/`, so
they bind every contributor and agent.

## Toolchain

`uv` (env/deps) · `ruff` (lint+format) · `mypy` (types, balanced strictness) ·
`pytest` + coverage (floor 80) · `prek` (git hooks). The plugin's own logic is
stdlib-only and shells out to the project's `uv run …`, so hooks work even before
the project's environment exists.

## Layout

```
.claude-plugin/plugin.json   manifest
commands/                    the 9 workflow commands
agents/                      doc-sync, quality, test-author, reference auditors
hooks/                       hooks.json + enforcement & injection scripts
lib/                         stdlib-only core (state, gate, env_scan, doc_claims, decisions, references, cmdscan)
bin/                         CLI entrypoints the commands call
references/                  starter style-reference library (django, cli, python-base)
templates/                   artifacts /forge:init scaffolds into a project
tests/                       the plugin's own test suite (stdlib + pytest)
```

## Developing the plugin

forge holds itself to the bar it enforces. Its core logic is unit-tested and the
checks run under the same toolchain it ships:

```bash
uv run --group dev pytest --cov   # tests + coverage (lib/)
uv run --group dev ruff check .   # lint
uv run --group dev mypy lib tests # types
```

The same gate runs at commit time via [prek](https://github.com/j178/prek)
(a faster pre-commit drop-in). Install the git hooks once:

```bash
uv run --group dev prek install   # then ruff + mypy + pytest run on every commit
```

## Installation

Add this directory as a plugin in Claude Code, then run `/forge:init` in a Python
project to adopt the workflow.
