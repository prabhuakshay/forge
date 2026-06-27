---
name: fastapi
summary: FastAPI application and route conventions
applies_to: ["src/**/api/**/*.py", "src/**/routers/**/*.py", "src/**/routes/**/*.py", "src/**/main.py", "src/**/app.py", "src/**/dependencies.py"]
enforcement: blocking
---
# FastAPI conventions

Conventions for FastAPI applications: routes, dependencies, schemas, and async.

## Routing & structure
- Group routes with `APIRouter` per resource, mounted in the app factory — not a
  single monolithic `main.py`. Tag and prefix each router.
- Keep path operations thin: validate via the schema, call a service/repository
  function, return a model. Business logic lives in importable functions, not in
  the endpoint body, so it's testable without an HTTP client.
- Use an app factory (`create_app()`) so tests and workers build isolated
  instances instead of importing a module-level singleton.

## Schemas (Pydantic)
- Separate request and response models; never accept or return ORM objects
  directly. Distinct models for create vs update vs read.
- Declare `response_model` on every operation so output is filtered and
  documented — don't leak internal fields by returning raw dicts.
- Validate and constrain at the schema (`Field` bounds, validators), not with
  hand-rolled checks inside handlers.

## Dependencies & config
- Acquire resources (db sessions, current user, settings) via `Depends`, not
  globals — it makes them overridable in tests via `app.dependency_overrides`.
- Configuration through `pydantic-settings`, injected as a dependency; never read
  `os.environ` ad hoc inside routes.
- Enforce authn/authz in dependencies shared across routers, not duplicated per
  endpoint.

## Async & blocking
- Endpoints that do I/O are `async def` and must `await` async clients. Never call
  blocking I/O (sync db drivers, `requests`, `time.sleep`) inside an `async`
  handler — it stalls the event loop; offload with `run_in_threadpool` or use an
  async client.
- Manage startup/shutdown resources with the `lifespan` handler, not deprecated
  event hooks.

## Errors & status codes
- Raise `HTTPException` (or a registered exception handler) with the correct
  status code; don't return error dicts with a 200. Use 201 for creation, 204 for
  empty responses.
- Don't leak internal exception detail or stack traces to clients; log the detail
  server-side and return a safe message.
