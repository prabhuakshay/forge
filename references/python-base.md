---
name: python-base
summary: Baseline Python conventions for all source in this repo
applies_to: ["src/**/*.py"]
enforcement: blocking
---
# Python baseline

Conventions every `.py` in `src/` follows. The auditor checks changed files
against these; violations in governed files are blocking.

## Typing
- Public functions and methods have complete type annotations (params + return).
- Prefer precise types over `Any`; reach for `Protocol`/`TypedDict`/generics
  before falling back to `Any`. An `Any` should be justifiable.
- Use `X | None` (not bare `Optional` import-soup); annotate with built-in
  generics (`list[str]`, not `List[str]`).

## Errors
- No bare `except:`; catch the narrowest exception that fits.
- Never silently swallow exceptions. If you catch-and-continue, log why or
  re-raise with context (`raise X from err`).
- Raise specific, meaningful exception types — not bare `Exception`.
- Validate inputs at the boundary; fail fast with a clear message.

## Structure
- One responsibility per function; if it needs a paragraph to explain, split it.
- No mutable default arguments (`def f(x=[])`). Use `None` + initialise inside.
- Prefer pure functions and explicit dependencies over hidden global state.
- Keep modules cohesive; a file that does five unrelated things should be several.

## Naming & comments
- Names reveal intent. A good name beats a comment that rescues a bad one.
- Comments explain *why*, never *what*. No stale comments, no commented-out code.
- Public modules/classes/functions carry a contract docstring (purpose, args,
  returns, raises) — not a line-by-line narration.

## Dependencies
- Don't reach for a new third-party dep when the stdlib covers it.
- Import at module top level unless there's a real reason (cycle, optional dep).
