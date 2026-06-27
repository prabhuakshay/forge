# Plan 0001 — Plugin enhancements: version agreement, security gate, override hygiene, configurable coverage floor, more references

**Goal:** Strengthen forge's push/publish gate and reference library by adding a
version-agreement check, a dependency/code security scan, override-history
hygiene, an env-configurable coverage floor, and three new style references.

Derived from a review of the plugin. Item 3 from that review (CI parity) is
explicitly **out of scope** at the user's request.

## Context / findings

- A real bug exists today: `pyproject.toml` is `0.10.0` but
  `.claude-plugin/plugin.json` and `marketplace.json` are `0.9.1`. The audit gate
  does not catch version drift — only `requires-python` vs mypy `python_version`.
- Coverage floor already exists (`lib/gate.py: COVERAGE_FAIL_UNDER = 80`,
  respecting a project's own `fail_under`). The genuine delta is making the
  default env-configurable.
- Override armed/consumed distinction already exists in `lib/status.py`; the gap
  is pruning old history and warning on pile-up.

## Out of scope

- CI parity (running gates server-side) — deferred at user's request.
- Changing how `bin/bump.py` writes versions — it stays the writer; the new check
  only *reads* and compares.

## Checklist

- [x] **Version agreement check.** New `lib/versions.py` collecting declared
  versions from `pyproject.toml [project]`, every `.claude-plugin/*.json`
  `"version"` field, and `src/**/__init__.py __version__`; a `disagreements()`
  helper. Wire a blocking `✗` into `bin/audit.py` when 2+ sites disagree.
  Verified by `tests/test_versions.py`.
- [x] **Dependency + code security scan.** New `lib/security.py`: `pip-audit`
  (dependency CVEs) and `bandit` (code) via `uv run`, both graceful-skip when the
  tool is absent (with a hint to add it). Wire a security section into
  `bin/audit.py` (findings are blocking `✗`). Verified by `tests/test_security.py`
  (parse sample JSON, assert skip path).
- [x] **python-security-auditor agent.** New `agents/python-security-auditor.md`
  (evidence-bound, general Python). Wire it into `commands/review.md` alongside
  the quality/reference auditors.
- [x] **Override hygiene.** `lib/state.py: prune_overrides(project, keep)`;
  `bin/override.py` gains `list` and `prune [N]` subcommands (back-compatible with
  `override <gate> [reason]`); `lib/status.py` warns when history is large.
  Document in `commands/override.md`. Verified in `tests/test_state.py` +
  `tests/test_bin.py`.
- [x] **Env-configurable coverage floor.** `lib/gate.py`: default floor reads
  `FORGE_COVERAGE_FLOOR` (fallback 80), still suppressed when the project sets its
  own. Verified in `tests/test_gate.py`.
- [x] **Three new references.** `references/fastapi.md`, `references/pytest.md`,
  `references/library.md` (packaging/library authoring), each with valid
  frontmatter (name, summary, applies_to, enforcement). Confirm they load via
  `bin/refs.py available` and pass `tests/test_references.py` expectations.
- [x] **Docs + changelog.** Update `commands/audit.md`, `commands/review.md`,
  `commands/override.md`, README reference list if present, and `CHANGELOG.md`.
- [x] **Fix the live version drift** by running `bin/bump.py 0.10.0` so all three
  manifests agree (the new audit check should then pass).

## Verification

- `lib/versions.py`, `lib/security.py`, state pruning, and the gate floor are
  unit-tested in `tests/`.
- `/forge:check` green (ruff + mypy + pytest, coverage ≥ floor on `lib/`).
- `python3 bin/audit.py` reports the version-agreement and security sections and
  is clean after the bump.
- `python3 bin/refs.py available` lists the three new references.
