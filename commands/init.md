---
description: Scaffold (or retrofit) a Python project with the forge workflow
argument-hint: "[project name]"
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

You are initialising the **forge** workflow in the current directory. Goal: a
consistent, gate-ready Python project where every artifact the audit later checks
exists from day one.

Templates live in `$CLAUDE_PLUGIN_ROOT/templates/`. Copy them in, substituting the
placeholders (`{{PROJECT_NAME}}`, `{{PACKAGE}}`, `{{DESCRIPTION}}`, `{{AUTHOR}}`,
`{{LICENSE}}`, `{{PYTHON_VERSION}}` like `3.12`, `{{PYTHON_VERSION_NODOT}}` like
`312`). Project name from `$ARGUMENTS` if given.

## Steps

1. **Gather facts.** Determine project name, a one-line description, the Python
   version (default to a current stable, e.g. 3.12), and license (default MIT).
   The package name is the project name normalised to a valid identifier
   (hyphens → underscores). If anything is ambiguous, ask with AskUserQuestion —
   don't guess the project's identity.

2. **Detect type** (library / web app / CLI / data-ML) from any existing files,
   or ask. This only tweaks dependencies and the architecture doc; the workflow
   is identical for all.

3. **Lay down the structure:**
   - `src/{{PACKAGE}}/__init__.py` (with a module docstring and `__version__`)
   - `tests/` with a trivial passing `test_smoke.py`
   - Copy & substitute: `pyproject.toml`, `.gitignore`, `.env.example`,
     `CHANGELOG.md`, `CLAUDE.md`, `README.md` (write a real quickstart),
     `.pre-commit-config.yaml`, `.github/workflows/ci.yml`,
     `scripts/check_env_sync.py`, and the whole `docs/` tree
     (`index.md`, `architecture.md`, `decisions/README.md`, `decisions/_template.md`).
   - Create `.forge/directives.md` from `templates/directives.md.tmpl`.

4. **Install style references** for the detected type. Use
   `/forge:reference add <name>` (or copy from `$CLAUDE_PLUGIN_ROOT/references/`)
   to install `python-base` always, plus `cli` for CLIs and `django` for Django
   projects — tuning each reference's `applies_to` globs to this repo's layout.

5. **Initialise tooling:** `git init` if not already a repo; `uv sync --all-extras`;
   `uv run prek install` to wire the commit hooks.

6. **Verify the floor:** run `/forge:check` once. It should be green on the smoke
   test. Fix anything that isn't.

7. **Report** the created structure and tell the user the loop:
   `/forge:plan → /forge:build → /forge:check → /forge:audit → /forge:release`,
   that design decisions are captured with `/forge:decide`, and that style
   references are managed with `/forge:reference`.

Do not invent product features or write speculative code — scaffold only.
