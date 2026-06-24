# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.5.0] - 2026-06-24

### Added
- **`/forge:status`** — a one-screen snapshot of where a project stands: phase
  and active plan, each gate (`check`/`audit`) as green-for-the-current-tree /
  stale / never-run, the dirty set, installed style references, the binding
  directive count, plus any *armed* one-shot override (about to fire) and recent
  override history. Pure read; the report builder lives in `lib/status.py`.
- **`/forge:override <gate> "<reason>"`** — an ergonomic, logged front door to
  the one-shot bypass mechanism the hooks already honour (gates: `check`,
  `audit`, `stop`, `plan`, `uv`). It arms `.forge/override-<gate>` with the
  reason baked in; the next matching gated action consumes it and records the
  bypass. Writing the sentinel by hand still works. The hook deny messages and
  `docs/state-schema.md` now point at the command.
- **`.forge/state.json` schema reference** ([docs/state-schema.md](docs/state-schema.md)):
  documents every key (gate fingerprint records, the dirty set, the override
  trail, per-session reference-injection tracking) and the override sentinel
  files, linked from the README.
- `bin/` CLI entrypoints now have a dedicated subprocess test suite
  (`tests/test_bin.py`) covering `check`, `mark`, `audit`, `refs`, `decide`, and
  `doc_claims` — previously only `bump` was tested.
- `FORGE_GATE_TIMEOUT` environment variable overrides the per-step gate
  subprocess timeout (default 600s) for projects whose suite runs long.

### Changed
- The **type-check step is now opt-in by configuration**. mypy runs only when the
  project configures it (`[tool.mypy]`, `mypy.ini`/`.mypy.ini`, or a `[mypy]`
  section in `setup.cfg`); otherwise the step is *skipped*, not failed. Previously
  `uv run mypy` on a project that never installed mypy would fail the gate for a
  tool it deliberately doesn't use. forge-scaffolded projects ship `[tool.mypy]`,
  so they keep type-checking unchanged.
- `/forge:check` no longer overrides a project's own coverage floor. forge's
  default `--cov-fail-under=80` is now applied only when the project doesn't
  declare its own `fail_under` (or `--cov-fail-under` in addopts), so a stricter
  project floor is never silently lowered.
- The `reference-auditor` now resolves overlapping references deterministically:
  `refs.py applicable` lists governing references most-specific-first (narrowest
  glob wins; `blocking` beats `advisory` on ties), and the agent prompt documents
  the precedence rule.

### Fixed
- `env_scan` now detects pydantic-settings fields at any indentation (tabs,
  2-space, 4-space), not only exactly 4 spaces, and ignores env reads that appear
  inside docstrings/triple-quoted strings — closing two drift-detection blind
  spots.
- `cmdscan` strips shell redirections (`2>`, `&>`, `>&`, `> file`) from parsed
  commands so a redirect target/fd can no longer leak into a command's argument
  list.
- `hookio.read_input` leaves a one-line stderr diagnostic when non-empty stdin
  fails to parse (instead of silently swallowing it) and coerces non-dict JSON to
  an empty payload; empty stdin stays silent.

## [0.4.0] - 2026-06-24

### Added
- **uv-only dependency enforcement.** A new `require_uv` PreToolUse hook blocks
  non-uv dependency commands (`pip install`, `uv pip install`, `poetry`/`pipenv`,
  `conda`, `pip-compile`, `easy_install`, …) in forge-enabled projects, steering
  all dependency changes through `uv add`/`uv remove` so `pyproject.toml` and
  `uv.lock` stay the single source of truth. Read-only commands (`pip list`,
  `uv pip freeze`) are untouched, and `.forge/override-uv` is the logged one-shot
  escape hatch. The policy is also stated as a binding rule in the `python-base`
  reference and the scaffolded `CLAUDE.md`.
- `cmdscan.dep_install_command()` — parses a Bash line and names the first
  non-uv dependency invocation it finds (reusing the tokenizer behind the
  commit/push guards).

## [0.3.0] - 2026-06-24

### Added
- `/forge:docs` command — crawls the codebase to find features with missing or
  thin markdown documentation, then writes or expands the relevant sections in
  `docs/` and `README.md`. Runs as an opt-out step at the end of `/forge:build`
  (skip with `--no-docs`).
- `doc-gap-scanner` agent (Haiku) — inventories what exists in the codebase vs
  what is covered in docs, returning a structured gap list for `/forge:docs`.

### Fixed
- `env_scan` false positives: test files (`tests/`) are now excluded from env-var
  scanning, and line comments are stripped before the regex runs. Previously,
  fixture strings in `test_env_scan.py` and example patterns in `env_scan.py`'s
  own comments were flagged as undocumented config.
- Added `.env.example` to the forge repo itself (forge has no runtime env config;
  the file is required by the audit scaffolding check).

## [0.2.1] - 2026-06-23

### Changed
- The `django` reference is restructured into two tiers: universal Django best
  practice (blocking) and a clearly separated, droppable "house stack" section for
  the org's opinionated library/architecture picks (django-environ, email/`full_name`
  User, services & selectors, FBVs, simple-history, WhiteNoise, Celery+Redis,
  debug-toolbar). A project installing the reference can drop the house tier without
  touching the universal rules.

## [0.2.0] - 2026-06-23

### Changed
- `/forge:release` now creates a GitHub release (`gh release create`) as a
  distinct step when the repo has a GitHub remote, alongside the package publish.
  Tagging, package publish, and GitHub release are now separate steps so a
  project can do any subset.

## [0.1.8] - 2026-06-22

### Added
- Unit tests for `bin/bump.py` (resolve arithmetic, field rewriting, end-to-end).
- CI schema-validates the plugin and marketplace manifests
  (`claude plugin validate .`), so a bad manifest fails CI instead of shipping.
- `homepage`, `repository`, and `license` in `.claude-plugin/plugin.json`.

### Changed
- The type-check gate now covers `bin/` too (`mypy lib tests bin`) — in the local
  gate, the prek hooks, and CI.

## [0.1.7] - 2026-06-22

### Added
- `bin/bump.py` — sets the version across all three manifests
  (`plugin.json`, `pyproject.toml`, and `marketplace.json`'s top-level and
  per-plugin entries) in one command, so they can't drift. The release checklist
  now uses it.

## [0.1.6] - 2026-06-22

### Added
- Plugin marketplace manifest (`.claude-plugin/marketplace.json`) so the plugin
  can be installed via `/plugin marketplace add prabhuakshay/forge`.

### Fixed
- `plugin.json` `author` is now an object (`{ "name": ... }`) as the plugin
  schema requires, instead of a bare string. Verified with
  `claude plugin validate .`.

## [0.1.5] - 2026-06-22

### Changed
- CI installs uv via its standalone shell installer (instead of the
  `astral-sh/setup-uv` action) and lets uv manage the matrix Python, so the
  workflow is fully off the deprecated Node 20 action runtime. Built-in uv
  caching was dropped as part of the change.

## [0.1.4] - 2026-06-22

### Added
- MIT `LICENSE` (and `license = "MIT"` in `pyproject.toml`).
- `release` and `python` badges in the README.

## [0.1.3] - 2026-06-22

### Changed
- CI: bump `actions/checkout` to v5 and `astral-sh/setup-uv` to v6 (off the
  deprecated Node.js 20 action runtime).

## [0.1.2] - 2026-06-22

### Documentation
- Release checklist now includes a `uv lock` / stage-`uv.lock` step so the
  release commit isn't bounced by the prek hook.

## [0.1.1] - 2026-06-22

### Added
- GitHub Actions CI badge in the README.

### Documentation
- `CHANGELOG.md` following Keep a Changelog.
- Release checklist at `docs/RELEASING.md`, linked from the README.

## [0.1.0] - 2026-06-22

First public release.

### Added
- **Workflow commands** — the nine-command loop: `/forge:init`, `/forge:plan`,
  `/forge:build`, `/forge:check`, `/forge:audit`, `/forge:review`,
  `/forge:release`, plus `/forge:decide` (durable intent) and `/forge:reference`
  (scoped style).
- **Hook-enforced gates** — PostToolUse auto-format + stale-result invalidation;
  PreToolUse blocks on un-green commit/push/publish and plan-less source edits;
  Stop blocks on a broken tree or undocumented env vars; SessionStart injects
  binding directives and the style-reference index. Every block has a logged
  one-shot override (`.forge/override-<gate>`).
- **Durable intent** — `/forge:decide` writes a binding directive
  (`.forge/directives.md`) plus a dated ADR (`docs/decisions/`); directives are
  re-injected each session and enforced in review.
- **Scoped style references** — `django`, `cli`, and `python-base` guides that
  govern files by glob, injected on edit and checked by the grounded
  `reference-auditor`. The `doc-sync-auditor` reports only `file:line`-grounded
  doc↔code drift.
- **Content-addressed fingerprint** — "green" is bound to a sha256 of source
  bytes rather than mtime, so a `git checkout`, branch switch, or fresh clone no
  longer spuriously invalidates a passing gate.
- **Incremental Stop gate** — type checks are scoped to the files changed since
  the last green check and skipped entirely when nothing is dirty.
- **Hardened command guards** — the commit/push/publish guards parse commands
  with `shlex` instead of regex: they catch `git -C <path> commit` and
  `bash -c 'git push'`, and no longer false-positive on a commit message that
  mentions "git push".
- **Test suite & dev tooling** — 129 tests (unit + subprocess-level hook
  integration) at ~90% coverage, a `prek` pre-commit config running the same
  gate, and GitHub Actions CI across Python 3.10–3.13.

[Unreleased]: https://github.com/prabhuakshay/forge/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/prabhuakshay/forge/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/prabhuakshay/forge/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/prabhuakshay/forge/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/prabhuakshay/forge/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/prabhuakshay/forge/compare/v0.1.8...v0.2.0
[0.1.8]: https://github.com/prabhuakshay/forge/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/prabhuakshay/forge/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/prabhuakshay/forge/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/prabhuakshay/forge/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/prabhuakshay/forge/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/prabhuakshay/forge/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/prabhuakshay/forge/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/prabhuakshay/forge/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/prabhuakshay/forge/releases/tag/v0.1.0
