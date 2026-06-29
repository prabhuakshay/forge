# forge

[![ci](https://github.com/prabhuakshay/forge/actions/workflows/ci.yml/badge.svg)](https://github.com/prabhuakshay/forge/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/prabhuakshay/forge?sort=semver)](https://github.com/prabhuakshay/forge/releases/latest)
[![python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)](https://github.com/prabhuakshay/forge/blob/main/pyproject.toml)

An opinionated **Python project workflow** as a Claude Code plugin. It makes the
quality bar *executable* and makes the agent run it on every loop — so projects
come out consistent, stable, well-documented, and honest about their own state.

## The loop

```
/forge:init  →  /forge:plan  →  /forge:build  →  /forge:check  →  /forge:review  →  /forge:audit  →  /forge:release
                     ▲                                                                                       │
                     └──────────────── /forge:decide (capture durable intent) ◄──────────────────────────────┘
```

| Command | Phase | Gate it satisfies |
|---|---|---|
| `/forge:init` | Scaffold a project (or retrofit one) with the full toolchain & docs | — |
| `/forge:plan` | Turn a request into an atomic checklist before any code | plan exists |
| `/forge:build` | Implement a plan item-by-item, tests from the spec | — |
| `/forge:check` | Code gate: ruff + mypy + pytest/coverage | **unblocks commit** |
| `/forge:audit` | Non-code sync: docs↔code, `.env`, lockfile, deps, metadata | **unblocks push/publish** |
| `/forge:review` | Quality + correctness + directive/reference compliance | **unblocks commit** (projects with directives or governing references) |
| `/forge:release` | Version bump, changelog, build, publish | — |
| `/forge:decide` | Record a durable directive + ADR | binds all future work |
| `/forge:reference` | Install/author scoped style references (django, cli, …) | catches style drift |
| `/forge:docs` | Crawl codebase, find undocumented features, write/expand markdown in docs/ | — |
| `/forge:status` | Snapshot of where the project stands: gates, dirty set, references, overrides | — |
| `/forge:override` | Arm a one-shot, logged bypass of a gate (check, audit, review, stop, plan, uv) | the audited escape hatch |

## What makes it stick

**The gates are enforced by hooks, not goodwill:**

- **PostToolUse** auto-formats every `.py` you touch in a forge-enabled project
  (`ruff format` + safe fixes) and invalidates any stale "green" result.
- **PreToolUse** blocks `git commit` unless `/forge:check` is green for the current
  tree, blocks `git push`/publish unless `/forge:audit` is green, blocks `git
  commit` unless `/forge:review` is green for projects that have binding directives
  or a governing style reference, blocks source edits with no active plan, and
  blocks non-uv dependency commands (pip, `uv pip install`, requirements files) —
  deps go through `uv add`/`uv remove`.
- **Stop** fires automatically when the agent tries to *end its turn* and won't
  let it stop on a broken tree. It runs format and lint (whole-tree) and the
  env-var drift check (vars read in code but undocumented in `.env.example`), plus
  — only when files have been edited since the last green check — mypy scoped to
  exactly those files (and skipped entirely when nothing is dirty, since types
  are already proven; mypy still follows imports out of the changed files, so a
  cross-file break is still caught). It deliberately skips the test suite, which
  is the slower commit gate's job. A failure isn't a wall: the reasons are fed
  back so the agent keeps working until the tree is green. If a broken state is a
  *deliberate* stopping point, `/forge:override stop "<why>"` releases it (logged).
- **SessionStart** injects the project's binding directives into every session.

Every block has a **logged one-shot override** so a real hotfix is never held
hostage — but the bypass is recorded, never silent. Arm one with `/forge:override
<gate> "<why>"` (or by writing the sentinel `.forge/override-<gate>` by hand); the
next matching gated action is allowed exactly once and the skip is appended to the
override trail in `.forge/state.json`. `/forge:status` shows what's armed before it
fires and the full history after.

**The gates are a workflow guardrail, not a security sandbox.** Two deliberate
properties follow from that. First, the hooks *fail open*: a hook that hits
malformed input or an unexpected error gets out of the way rather than wedging your
tool call. Second, the command parser that recognises `git commit` / `git push` /
non-uv dependency commands is built to see through ordinary command shapes (paths,
env prefixes, wrappers, `sh -c '…'`), not determined obfuscation — exotic quoting or
an `eval` can still slip past it. This is by design: forge keeps an honest workflow
honest and makes the quality bar the path of least resistance; it is not an
adversarial boundary. What it *does* guarantee is that every bypass that happens
through the front door is logged, never silent.

The type check (mypy) only runs when the project actually configures it — a
`[tool.mypy]` table, a `mypy.ini`/`.mypy.ini`, or a `[mypy]` section in
`setup.cfg`. A project
that doesn't type-check isn't forced red on a tool it doesn't use; forge-scaffolded
projects ship the config, so they stay covered.

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
covers your Django code, `cli.md` your CLI code, `python-base.md` all Python
source (`src/**/*.py` by default — tune the glob for your layout). They
work two ways: the relevant reference is **injected into context the moment you
edit a file it governs** (once per session), and the grounded `reference-auditor`
checks changed files against them at review time. A `blocking` reference's rules
are mandatory; `advisory` ones warn. Author your own with
`/forge:reference create`. This is how style drift gets caught the same way doc
and config drift do — references travel with the repo in `.forge/references/`, so
they bind every contributor and agent.

**Two agents are *evidence-bound*; the rest are advisory.** "Grounded by design"
is a property of the two auditors that gate-adjacent work depends on: the
`doc-sync-auditor` and the `reference-auditor` must tie every finding to a
concrete `file:line` (or mark it `UNVERIFIABLE`), so they report real drift
without hallucinating. The other agents are deliberately *not* held to that bar
because their job is different: `python-quality-auditor` is a reviewer's opinion,
`doc-gap-scanner` reports what's *absent* (which has no line to cite), and
`python-test-author` *writes* tests from a spec. Treat the first two as detectors
you can trust to be literal, and the rest as proposers whose output you read.

## Toolchain

`uv` (env/deps) · `ruff` (lint+format) · `mypy` (types, balanced strictness) ·
`pytest` + coverage (floor 80) · `prek` (git hooks). The plugin's own logic is
stdlib-only and shells out to the project's `uv run …`, so hooks work even before
the project's environment exists.

## Requirements

- **Python projects only.** Every gate is built around the Python toolchain
  above; forge has nothing to enforce on a non-Python repo.
- **Linux and macOS only (POSIX).** The hooks invoke `python3` and the workflow
  state is guarded by POSIX file locking (`fcntl`), so concurrent tool calls
  can't corrupt it. Windows is not supported.

## Layout

```
.claude-plugin/plugin.json   manifest
commands/                    the workflow commands
agents/                      doc-sync, doc-gap-scanner, quality, security, test-author, reference auditors
hooks/                       hooks.json + enforcement & injection scripts
lib/                         stdlib-only core (state, fingerprint, gate, env_scan, doc_claims, decisions, references, cmdscan, hookio, status, security, versions)
bin/                         CLI entrypoints the commands call
references/                  starter style-reference library (django, cli, python-base, fastapi, library, pytest)
templates/                   artifacts /forge:init scaffolds into a project
tests/                       the plugin's own test suite (stdlib + pytest)
```

Per-project workflow state lives in `.forge/state.json`; its schema (gate
fingerprints, the dirty set, the override trail) is documented in
[docs/state-schema.md](docs/state-schema.md).

## Developing the plugin

forge holds itself to the bar it enforces. Its core logic is unit-tested and the
checks run under the same toolchain it ships:

```bash
uv run --group dev pytest --cov   # tests + coverage (lib/)
uv run --group dev ruff check .   # lint
uv run --group dev mypy lib tests bin # types
```

The same gate runs at commit time via [prek](https://github.com/j178/prek)
(a faster pre-commit drop-in). Install the git hooks once:

```bash
uv run --group dev prek install   # then ruff + mypy + pytest run on every commit
```

Cutting a release? Follow the checklist in [docs/RELEASING.md](docs/RELEASING.md).

## Installation

Install from the plugin marketplace inside Claude Code:

```text
/plugin marketplace add prabhuakshay/forge
/plugin install forge@forge
```

The first command registers this repo as a marketplace; the second installs the
`forge` plugin from it (`forge@forge` is `<plugin>@<marketplace>`). To update
later, re-run `/plugin marketplace update forge`.

Prefer a local checkout? Clone the repo and add the directory as a plugin in
Claude Code instead.

Then run `/forge:init` in a Python project to adopt the workflow.
