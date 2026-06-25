# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.9.1] - 2026-06-25

### Fixed
- **Concurrent `/forge:decide` runs can no longer collide on an ADR number.**
  `next_adr_number` scanned `docs/decisions/` with no lock while every other
  state mutation was serialised, so two decisions racing on a read-modify-write
  could both claim `0004` — producing duplicate ADRs and a directive whose
  back-reference is ambiguous, corrupting the audit trail the feature exists to
  protect. Allocation and the ADR/directive/index writes now run together under
  the shared `.forge` lock (`state.locked`), via a new `decisions.record_decision`.
  The ADR is also written atomically (temp + `os.replace`) and first, so a crash
  between steps can at worst orphan an ADR file — never leave a directive pointing
  at a number that was never written.
- **The coverage-floor check no longer trips on a comment.** `/forge:check`
  decided whether a project sets its own coverage floor with a bare substring scan
  of `pyproject.toml`, so a `--cov-fail-under` sitting in a comment (or a stray
  `fail_under` in an unrelated table) wrongly suppressed forge's default floor.
  Detection is now section-scoped: `fail_under` only counts inside
  `[tool.coverage.report]`, `--cov-fail-under` only inside
  `[tool.pytest.ini_options]`, and whole-line comments are ignored.
- **The commit-time gate now measures coverage like the rest.** forge's own prek
  `pytest` hook ran without `--cov`, so coverage was checked in-session and in CI
  but not at commit — contradicting the README's "the same gate runs at commit
  time." The hook now runs `pytest -q --cov`.

### Changed
- **Clearer command guidance.** `/forge:build` now states the two `--no-docs`
  skip conditions as independent (explicit opt-out vs. auto-skip when no
  production source changed); `/forge:init` lists concrete type-detection markers
  (`manage.py`/web framework → web app, `[project.scripts]`/`__main__.py` → CLI,
  pandas/numpy/torch → data-ML, else library) instead of "from any existing
  files"; and the scaffolded `CLAUDE.md` now documents the `scripts/check_env_sync.py`
  env-sync guard that was already wired into the pre-commit config.

## [0.9.0] - 2026-06-25

### Fixed
- **The green-gate fingerprint no longer misses a same-second edit.** A new
  stat-keyed digest cache speeds up `code_fingerprint`, but a naive `(mtime,
  size)` cache would wrongly trust a same-size edit that lands in the same
  clock-granularity tick as the last hash (the classic "racy clean" problem — and
  not theoretical: fast/tmpfs writes hit it). The cache now applies git's rule —
  an entry is trusted only when the file's mtime is in a *strictly earlier whole
  second* than the recorded cache build time — so a same-second change is always
  re-hashed and the content-addressed guarantee is never weakened.

### Changed
- **Workflow state is now concurrency-safe.** Claude Code can run tools (and
  therefore hooks) at once; two updaters racing on a read-modify-write of
  `.forge/state.json` could let the second `os.replace` silently drop the first's
  change — a lost `dirty_py` entry, or worse a dropped `overrides` audit record.
  Every state mutation now runs under an exclusive POSIX advisory lock
  (`state.locked`, a `.forge/.state.lock` sidecar), so updates serialise instead
  of clobbering each other.
- **`code_fingerprint` only re-reads what changed.** The per-commit hash was
  reading and SHA-256-ing every first-party `.py` on each gate check; it now skips
  files whose size and mtime prove they weren't touched since the last build (via
  a git-ignored `.forge/fpcache.json` cache), keeping the cost proportional to
  what changed rather than to repo size. The fingerprinting logic moved into a new
  dependency-free `lib/fingerprint.py`; `state` re-exports `code_fingerprint`, so
  callers are unchanged.

### Documentation
- README now states forge's platform requirements plainly: **Python projects
  only**, and **Linux/macOS only** — the hooks invoke `python3` and the workflow
  state relies on POSIX file locking (`fcntl`), so Windows is unsupported. The
  plugin manifests carry the same constraint in their description and keywords.
- `docs/state-schema.md` documents the two new local-only sidecar files
  (`.state.lock`, `fpcache.json`), including the cache structure and its
  racy-clean guard.

### Internal
- A meta-test (`tests/test_command_refs.py`) now asserts the prompt layer stays
  wired up: every `bin/*.py` a command invokes, every agent it names, and every
  script in `hooks.json` must resolve to a real file — so a rename or typo there
  can't ship undetected.

## [0.8.0] - 2026-06-25

### Changed
- **`env_scan` detects the env reads it was silently missing.** The drift scan
  now recognises `os.environ.pop(...)` and `os.environ.setdefault(...)` (both read
  the variable, just like `.get()`), and captures variable names in *any* case
  rather than `UPPER_CASE` only. Environment variables are case-sensitive on
  POSIX, so a read like `os.getenv("debug_mode")` is real config that onboarding
  must document; matching only `[A-Z…]` quietly dropped every lower/mixed-case
  read on the floor. The drift check compares names verbatim, matching how the OS
  resolves them (pydantic-settings stays case-folded, since it resolves env vars
  case-insensitively). This makes the `/forge:audit` env check and the Stop gate's
  drift check catch undocumented configuration they previously let through.

### Removed
- **`lib/state.clear_dirty`** — dead code with no caller (`record_pass` clears the
  dirty set inline). Removing it trims the internal surface; no command, hook, or
  documented behaviour referenced it.

### Documentation
- README now states plainly that only two agents are *evidence-bound* — the
  `doc-sync-auditor` and `reference-auditor` must cite a `file:line` for every
  finding — while `python-quality-auditor`, `doc-gap-scanner`, and
  `python-test-author` are advisory/generative, so the "grounded" claim no longer
  reads as covering the whole agent fleet.
- README's **Stop gate** description now says when it fires (on turn-end), what it
  runs (format/lint/types scoped to changed files, plus env drift — not the test
  suite), and that failures are fed back rather than walling off.
- `docs/state-schema.md` documents that `dirty_py` is cleared **only** by a green
  `check` (which runs the tests), so it intentionally accumulates across a session
  past `audit`/`review` passes — bounded to real files and correct because mypy
  follows imports.
- `/forge:docs` report header no longer looks like a subcommand
  (`/forge:docs complete` → `Documentation pass complete`); `/forge:release` now
  gives the concrete command for listing commits since the last tag.
- README's `lib/` layout list now includes the `status` module (it backs
  `/forge:status`) — caught by the doc-sync auditor during this release.

### Internal
- Closed the remaining branch-coverage gaps in `lib/cmdscan` (shell-with-script,
  boolean git globals, bare `git`, glued `-m` modules) and `lib/state`
  (unreadable source file, corrupt `dirty_py`, double-failure temp cleanup):
  `cmdscan` 91%→98%, `state` 89%→96%, suite total 94%→96%.

## [0.7.0] - 2026-06-25

### Added
- `bin/plan.py active <path>` — records the active plan via a helper so
  `/forge:plan` no longer hand-edits `state.json` (a malformed write there
  corrupted workflow state); backed by `lib/state.set_active_plan`.

### Changed
- **State is now persisted atomically** (`lib/state.save` writes a temp file then
  `os.replace`s it). A torn write was previously read back as corrupt JSON and
  silently reset to the empty skeleton — dropping recorded passes *and* the
  overrides audit trail — and concurrent tool calls could lose each other's
  writes.
- **`require_plan` only treats a plan with unchecked items as active.** A
  completed plan (every item ticked) or an empty file no longer holds the gate
  open, so finishing a plan correctly re-demands a new one before more source is
  written.
- **`auto_format` is scoped to forge-enabled projects** (a `.forge/` dir), like
  every other hook — no more silent `ruff` runs on `.py` edits in unrelated repos.
- **Gates check freshness before consuming an override.** `require_check`,
  `require_review`, `require_audit`, and `require_plan` now confirm the gate is
  actually unsatisfied before taking a one-shot override, so a green/satisfied
  action never burns (and never falsely logs) a bypass that wasn't needed.
- **`require_review` decodes git's C-quoted paths** (octal-escaped non-ASCII /
  special filenames) before matching them against reference globs, so the
  reference half of the gate no longer misses a governed file with such a name.

### Documentation
- Propagated the review gate into the places it had drifted from: `/forge:status`
  command doc, the scaffolded `CLAUDE.md` template, and the canonical loop string
  in `/forge:init`.
- `doc-gap-scanner` no longer assumes the plugin's own layout (`commands/`,
  `agents/`, `bin/`) — `src/**` is the universal case; plugin-only kinds are
  optional.

## [0.6.0] - 2026-06-25

### Added
- **Review gate (`require_review`)** — `git commit` is now blocked until
  `/forge:review` is green for the current tree, closing the gap where binding
  directives and blocking style references were enforced only by an optional
  command. It binds **only** where there's something to enforce (option B): a
  recorded directive, or an installed reference governing a file in the change
  set — projects with neither are unaffected. Like the other gates it works on a
  fingerprinted pass (`last_review`, recorded by `/forge:review` via
  `bin/mark.py review`), is invalidated by any `.py` edit, and honours a one-shot
  logged override (`/forge:override review "<why>"`). `/forge:status` surfaces the
  review gate when it applies.
- `lib/decisions.binding_directive_count` / `has_binding_directives` — distinguish
  a project that has actually recorded a directive from one that only carries the
  scaffolded template prose (the signal the review gate keys on). `/forge:status`
  now uses this for its directive count.

### Changed
- `references.for_file` breaks an equal-specificity tie deterministically:
  `blocking` references outrank `advisory` ones (then name), and the
  `reference-auditor` documents the rule.
- `/forge:init` pins the default Python version (3.13) instead of "a current
  stable, e.g. 3.12"; `/forge:build` documents that it is resumable (works only
  unchecked items).

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

[Unreleased]: https://github.com/prabhuakshay/forge/compare/v0.9.1...HEAD
[0.9.1]: https://github.com/prabhuakshay/forge/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/prabhuakshay/forge/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/prabhuakshay/forge/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/prabhuakshay/forge/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/prabhuakshay/forge/compare/v0.5.0...v0.6.0
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
