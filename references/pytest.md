---
name: pytest
summary: Test design and pytest conventions
applies_to: ["tests/**/*.py", "**/test_*.py", "**/*_test.py", "**/conftest.py"]
enforcement: advisory
---
# Test design (pytest)

Conventions for tests written with pytest. Tests are the executable spec — they
must be as clear and honest as the code they guard.

## Structure
- One behaviour per test; the name says what it asserts (`test_<unit>_<condition>_
  <expected>`), not how. A test you can't name precisely is testing too much.
- Arrange–act–assert, visibly separated. Keep the *act* a single call so a failure
  points at one thing.
- Group related tests in a class only when they share fixtures or setup; don't nest
  for taxonomy alone.

## Fixtures & isolation
- Share setup through fixtures in `conftest.py`, not module-level globals or
  copy-paste. Scope fixtures as narrowly as correctness allows (`function` by
  default).
- Each test is independent and order-free: no reliance on another test's side
  effects, no shared mutable state leaking between tests.
- Use `tmp_path`/`tmp_path_factory` for filesystem work and `monkeypatch` for env
  and attributes — never mutate the real environment or cwd irreversibly.

## Assertions
- Assert on observable behaviour and public contracts, not private internals — a
  test bound to implementation breaks on every refactor and proves nothing.
- One logical assertion per test; prefer specific equality over truthiness.
- Use `pytest.raises(...)` (matching the message where it matters) for error
  paths; assert the *contract*, not the traceback.

## Parametrisation & coverage
- `@pytest.mark.parametrize` for the same logic over many inputs instead of copied
  test bodies; give cases `ids` so failures are readable.
- Cover the edge and error paths, not just the happy one. A green suite that only
  exercises success is a false signal.

## Test doubles
- Mock at the boundary you own (the seam), not three layers deep. Over-mocking
  tests the mocks, not the code.
- Prefer real objects and fakes to mocks when they're cheap; reserve mocks for
  slow, non-deterministic, or external dependencies.
