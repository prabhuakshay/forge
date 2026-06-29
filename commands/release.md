---
description: Cut a release — bump version, update changelog, build, publish
argument-hint: "[major|minor|patch, default patch]"
allowed-tools: Bash, Read, Edit
---

Cut a release. The push/publish steps are gated on a green `/forge:audit`, so do
not attempt to bypass that — resolve drift instead.

## Preconditions

1. `/forge:check` is green (tests/types/lint pass).
2. `/forge:audit` is green (docs, config, deps, metadata in sync). If not, run it
   and fix the findings first — the require_audit hook will block publish otherwise.

## Steps

1. **Decide the bump** from `$ARGUMENTS` (default `patch`) and SemVer: breaking →
   major, feature → minor, fix → patch. List the commits since the last release
   to sanity-check the level — `git log "$(git describe --tags --abbrev=0)"..HEAD
   --oneline` (if the repo has no tags yet, `git log --oneline` over the whole
   history). A breaking change among them forces a higher bump than the argument
   asked for; say so rather than under-bumping.
2. **Update the version** in `pyproject.toml` (and `src/<pkg>/__init__.py` if it
   carries `__version__`). Keep them in agreement.
3. **Update `CHANGELOG.md`:** move `Unreleased` entries under a new `## [X.Y.Z] -
   <date>` section. If anything notable since the last tag is missing, add it —
   warn the user rather than shipping an incomplete changelog. Record only the
   *net* change a user sees in this release, not intra-release churn: if something
   was added and then removed within the same release, list neither; if something
   was added and then fixed within the same release, list only the final
   working feature, not the fix.
4. **Commit** the bump and changelog with a conventional-commit message:
   `git commit -m "chore(release): release vX.Y.Z"`. Let any pre-commit gate run;
   don't bypass it.
5. **Build:** `uv build`. Confirm the artifacts.
6. **Tag** only if the user asked to publish: create the annotated version tag
   (`git tag -a vX.Y.Z`) and push it. Publishing is outward-facing and
   irreversible — confirm with the user before this and the steps below.
7. **Publish the package:** `uv publish` (or the project's configured target).
   Skip if the project isn't distributed as a package.
8. **Create the GitHub release** if the repo has a GitHub remote: `gh release
   create vX.Y.Z --title "vX.Y.Z" --notes-file <notes>`, using the changelog
   section from step 3 as the notes. Skip if there's no GitHub remote.

Report the new version, the changelog section, and what was (or wasn't) published
— both to the package target and to GitHub.
