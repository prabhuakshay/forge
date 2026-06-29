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
- [ ] Gate is green locally: `uv run --group dev ruff check . && uv run --group dev ruff format --check . && uv run --group dev mypy lib tests bin && uv run --group dev pytest --cov`.
- [ ] Manifests valid: `claude plugin validate .`.
- [ ] CI is green for the tip commit (the same gate across Python 3.10–3.13).

## Steps

1. [ ] **Bump the version** with `python3 bin/bump.py X.Y.Z` (or `patch` /
   `minor` / `major`). One command sets the version in all three files that
   record it — `.claude-plugin/plugin.json`, `pyproject.toml`, and
   `.claude-plugin/marketplace.json` (its top-level version *and* each plugin
   entry) — so they can't drift apart. Re-run `claude plugin validate .` after.
2. [ ] **Refresh the lockfile:** run `uv lock` so `uv.lock` records the new
   version, and stage it. Skipping this gets the release commit *bounced by the
   prek hook* — `uv run` regenerates `uv.lock` mid-hook, and prek fails any hook
   that modifies a tracked file. Doing it up front keeps the commit clean.
3. [ ] **Update `CHANGELOG.md`:** move everything under `## [Unreleased]` into a
   new `## [X.Y.Z] - YYYY-MM-DD` section. Add anything notable that's missing
   rather than shipping an incomplete changelog. Record only the *net* change a
   user sees in this release, not intra-release churn: if something was added and
   then removed within the same release, list neither; if something was added and
   then fixed within the same release, list only the final working feature, not
   the fix. Update the compare/release links at the bottom (`[Unreleased]` →
   `compare/vX.Y.Z...HEAD`, add `[X.Y.Z]`).
4. [ ] **Commit** the bump: `git commit -m "chore(release): release vX.Y.Z"` (the
   prek hook runs the gate; let it pass, don't bypass).
5. [ ] **Push** and wait for CI to go green: `git push`.
6. [ ] **Tag** the released commit annotated, and push the tag:
   `git tag -a vX.Y.Z -m "forge vX.Y.Z" && git push origin vX.Y.Z`.
7. [ ] **Create the GitHub release** from the tag with written notes:
   `gh release create vX.Y.Z --title "vX.Y.Z" --notes-file <notes>`
   (use `--generate-notes` only as a starting point — prefer a real summary; see
   the v0.1.0 release for the house style).
8. [ ] **Verify:** `gh release view vX.Y.Z` shows the right tag, not a draft, and
   the README CI badge is green.

## Notes

- **No PyPI publish.** If forge is ever distributed as a package, add a
  `uv build` + `uv publish` step here; until then the GitHub release is the
  artifact. `uv publish`/`git push` are gated on a green `/forge:audit` by the
  `require_audit` hook.
- **Overrides leave a trail.** If a release genuinely must bypass a gate, use the
  logged `.forge/override-<gate>` escape hatch — never silently work around it.
