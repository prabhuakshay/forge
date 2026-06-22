# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/prabhuakshay/forge/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/prabhuakshay/forge/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/prabhuakshay/forge/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/prabhuakshay/forge/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/prabhuakshay/forge/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/prabhuakshay/forge/releases/tag/v0.1.0
