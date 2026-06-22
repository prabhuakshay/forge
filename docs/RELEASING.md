# Releasing forge

This is the concrete checklist for cutting a forge release. It mirrors the
`/forge:release` command and adds the steps specific to this repo (prek, CI, the
GitHub release). forge is a Claude Code plugin, not a PyPI package, so "publish"
here means **tag + GitHub release**, not `uv publish`.

## Versioning

Semantic Versioning. Pick the bump from what changed since the last tag:

- **major** — a breaking change to a command's contract, a hook's behaviour, or
  the on-disk `.forge/` layout.
- **minor** — a new command, hook, reference, or other backward-compatible
  capability.
- **patch** — a bug fix or internal change with no user-visible contract change.

## Preconditions

- [ ] On `main`, working tree clean, up to date with `origin`.
- [ ] Gate is green locally: `uv run --group dev ruff check . && uv run --group dev ruff format --check . && uv run --group dev mypy lib tests && uv run --group dev pytest --cov`.
- [ ] CI is green for the tip commit (the same gate across Python 3.10–3.13).

## Steps

1. [ ] **Bump the version** in `.claude-plugin/plugin.json` (`version`) and in
   `pyproject.toml` (`[project] version`). Keep them in agreement — they're the
   two sources of truth for the plugin.
2. [ ] **Update `CHANGELOG.md`:** move everything under `## [Unreleased]` into a
   new `## [X.Y.Z] - YYYY-MM-DD` section. Add anything notable that's missing
   rather than shipping an incomplete changelog. Update the compare/release links
   at the bottom (`[Unreleased]` → `compare/vX.Y.Z...HEAD`, add `[X.Y.Z]`).
3. [ ] **Commit** the bump: `git commit -m "Release vX.Y.Z"` (the prek hook runs
   the gate; let it pass, don't bypass).
4. [ ] **Push** and wait for CI to go green: `git push`.
5. [ ] **Tag** the released commit annotated, and push the tag:
   `git tag -a vX.Y.Z -m "forge vX.Y.Z" && git push origin vX.Y.Z`.
6. [ ] **Create the GitHub release** from the tag with written notes:
   `gh release create vX.Y.Z --title "vX.Y.Z" --notes-file <notes>`
   (use `--generate-notes` only as a starting point — prefer a real summary; see
   the v0.1.0 release for the house style).
7. [ ] **Verify:** `gh release view vX.Y.Z` shows the right tag, not a draft, and
   the README CI badge is green.

## Notes

- **No PyPI publish.** If forge is ever distributed as a package, add a
  `uv build` + `uv publish` step here; until then the GitHub release is the
  artifact. `uv publish`/`git push` are gated on a green `/forge:audit` by the
  `require_audit` hook.
- **Overrides leave a trail.** If a release genuinely must bypass a gate, use the
  logged `.forge/override-<gate>` escape hatch — never silently work around it.
