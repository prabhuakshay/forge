---
name: library
summary: Conventions for publishable Python libraries and packaging
applies_to: ["src/**/__init__.py", "src/**/py.typed", "pyproject.toml"]
enforcement: advisory
---
# Library & packaging conventions

For code meant to be imported by others (a published package), not an application.
The public API is a contract — treat changes to it with the weight that implies.

## Public API
- The public surface is explicit: define `__all__` in each public module, and
  expose the supported API from the package `__init__.py`. Everything else is
  private (prefix with `_`) and may change without notice.
- Keep the import side-effect-free: importing the package must not read files, hit
  the network, configure logging, or mutate global state. Do that in functions the
  caller invokes.
- Don't leak third-party types through your public signatures unless they're part
  of the contract — wrap them, so a dependency swap isn't a breaking change.

## Typing
- Ship type information: full annotations on the public API and a `py.typed`
  marker so downstream type-checkers use them. A typed library is a documented one.
- Prefer precise, narrow types in signatures; accept the general (`Iterable`),
  return the specific (`list`).

## Versioning & compatibility
- Follow SemVer: breaking changes bump major, additive changes minor, fixes patch.
  A single source of truth for the version (read from package metadata; don't
  duplicate the string across files).
- Deprecate before removing: warn with `DeprecationWarning`, document the
  replacement and the removal version, then remove on the next major.
- Don't break import paths or signatures in a minor/patch release.

## Dependencies & metadata
- Depend on the minimum needed; specify compatible-release ranges, not pinned
  exact versions (pinning belongs in applications, not libraries).
- Keep optional features behind extras (`[project.optional-dependencies]`) rather
  than forcing every user to install everything.
- Complete packaging metadata: description, readme, license, `requires-python`,
  and classifiers — so the package is discoverable and installs on the right
  interpreters.

## Errors & logging
- Raise a defined exception hierarchy rooted at a package-specific base exception,
  so callers can catch your errors precisely.
- A library logs to a `NullHandler`-attached logger named for the package; it
  never configures the root logger or prints — output policy is the application's
  choice.
