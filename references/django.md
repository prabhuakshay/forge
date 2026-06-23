---
name: django
summary: Django conventions — universal best practice (blocking) plus this org's opinionated default stack
applies_to:
  - "**/models.py"
  - "**/models/**/*.py"
  - "**/services.py"
  - "**/services/**/*.py"
  - "**/selectors.py"
  - "**/selectors/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
  - "**/urls.py"
  - "**/forms.py"
  - "**/admin.py"
  - "**/migrations/*.py"
  - "**/settings.py"
  - "**/settings/**/*.py"
  - "**/management/commands/*.py"
  - "**/templates/**/*.html"
enforcement: blocking
---
# Django conventions

This reference has two tiers. The **universal conventions** apply to any Django
project and are enforced as blocking. The **house stack** at the end is this org's
default library and architecture picks — expected in our projects, but the
swappable tier: a new project can drop or replace any of them on install without
touching the universal rules above them.

## Guiding principle
- **Prefer simple, stable, readable code over clever or terse code.** If a junior
  has to think hard to follow it, rewrite it. Boring and obvious beats short and
  smart — it is cheaper to debug and safe to change.
- Stay close to idiomatic Django. Don't invent abstractions the framework already
  provides.

## Settings & project structure
- One env-driven settings module. All secrets and environment-specific values come
  from the environment — never hardcoded. Every var is documented in `.env.example`.
- `DEBUG` defaults to `False`; `ALLOWED_HOSTS` is read from config, never `["*"]`.
- `USE_TZ = True`; store timezone-aware datetimes, never naive.
- Define a **custom User model** in the first migration — swapping it later is
  painful and migration-heavy.
- Apps are organized by domain and stay focused; no god-app.
- Target a Django **LTS** release; pin Django and Python versions.

## Models
- Models hold **data only**: fields, constraints, relationships, `__str__`, simple
  derived `@property`, and `clean()` validation. No business logic, no cross-model
  orchestration, no side effects.
- Every model defines `__str__`. Set `Meta.ordering` explicitly if order matters.
- Prefer DB-level constraints (`UniqueConstraint`, `CheckConstraint`) over app-only
  validation for invariants.
- Money is `DecimalField`, never `float`. Use the right field type; avoid
  `null=True` on string fields (use `blank=""`).
- Name every reverse relation with `related_name`.
- Index fields used in filters, ordering, and foreign keys.

## Business logic placement
- **Keep business logic out of models and views.** Models hold data; views handle
  HTTP. Writes, side effects, and reusable queries live in a dedicated logic layer
  (this org's convention for that layer is in the house stack below).
- Wrap multi-write operations in `transaction.atomic`.
- Call effectful logic **explicitly at the call site**. Avoid `post_save`/`pre_save`
  signals for business logic — reserve signals for genuinely decoupled cross-cutting
  concerns only.

## Queries / ORM
- **Never query in a loop.** Use `select_related` (FK/1-1) and `prefetch_related`
  (M2M/reverse) to kill N+1.
- Don't over-fetch: `.only()`/`.defer()`/`.values()` where it counts; `.exists()`
  over `len(qs)`; `.count()` over `len(list(qs))`.
- Use `F()` expressions for atomic increments; never read-modify-write a counter.
- Use `bulk_create`/`bulk_update` for batches instead of per-row saves.
- Use `get_or_create`/`update_or_create` (backed by a unique constraint) instead of
  check-then-create, which races.

## Views, URLs & forms
- Keep views **thin**: validate input, call the logic layer, return a response.
- **All** user input is validated through a Form/Serializer — never trust
  `request.POST` / `request.data` / query params raw.
- Enforce authorization explicitly; never trust a client-supplied object id without
  an ownership/permission check. Use `get_object_or_404`.
- Name all URLs; build links with `{% url %}` / `reverse()`, never hardcoded paths.
- Paginate every list view/endpoint; never hand an unbounded queryset to a template
  or API response.

## Templates, static & frontend
- **Vendor all JS/CSS locally** — no `<script src="https://cdn...">`. Self-host so
  the app works offline, survives CDN outages, and allows a strict CSP. Commit and
  pin vendored asset versions.
- Reference every asset via `{% static %}`; use a manifest static storage for
  cache-busting hashes. `collectstatic` runs at deploy; never `runserver` in
  production.
- Autoescaping stays on; never pipe user data through `|safe` / `mark_safe`.
- Every POST form includes `{% csrf_token %}`.
- Keep logic out of templates — no queries or business logic. Use template
  inheritance (`base.html` + blocks).
- Use `{# ... #}` for single-line comments and `{% comment %} ... {% endcomment %}`
  blocks for multi-line comments — never HTML `<!-- -->` (it leaks to output).

## Security
- Use the ORM / parameterized queries; never string-format user input into SQL
  (`.raw()` / `.extra()` need a documented reason).
- Production HTTPS hardening: `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`
  (+ subdomains/preload), `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
  `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS = "DENY"`.
- Keep Django's password validators enabled; never store or log secrets/PII.
- Rate-limit authentication and other abuse-prone endpoints.

## Migrations
- Migrations are reviewed code — no autogenerated cruft committed blindly. Name
  them meaningfully.
- Separate schema changes from data migrations; make data migrations reversible or
  document why not.
- No destructive operations (drop column/table, irreversible data change) without a
  deliberate, noted decision.

## Email, management commands & admin
- **Email:** render bodies from templates; use the console backend in dev. Send
  through the logic layer and off the request cycle (see the house stack for the
  queue), never inline in a view.
- **Management commands** are thin wrappers that call the logic layer — no business
  logic inline. Make them idempotent where possible.
- **Admin:** configure `list_display`, `list_filter`, `search_fields`, and
  `list_select_related` (admin is a top N+1 source). Mark computed/sensitive fields
  `readonly_fields`; restrict admin to staff and don't expose secrets.

## Ops / performance
- Background/slow work (email, exports, third-party calls) runs off the request
  cycle via the project's task queue, not inline.
- Configure structured logging via `LOGGING`; never `print`. Wire an error tracker.
- Set `CONN_MAX_AGE` / pooling for DB connections; run under a production WSGI/ASGI
  server with a real worker count — never `runserver` in production.
- Cache deliberately (per-view, template fragment, or low-level) **with** an
  invalidation strategy — no unbounded caches.

## Dependencies & tooling
- `ruff` and `mypy` stay clean; pin all dependencies via a lockfile.

---

# House stack (opinionated defaults)

The org's default picks. Expected in our projects, but the **swappable tier** — a
new project may drop or replace any of these on install without affecting the
universal rules above. If a rule above says "the logic layer" or "the project's
task queue," this is what it resolves to here.

- **Settings:** `django-environ` for env parsing.
- **User model:** email-based (`USERNAME_FIELD = "email"`, no `username`) with a
  single **`full_name`** field — not `first_name`/`last_name`.
- **Logic layer — services & selectors:** a *service* performs a write or
  side-effectful operation (e.g. `invoice_issue(*, invoice, user)`), takes keyword
  args, and wraps its writes in `transaction.atomic`. A *selector* returns data,
  often a queryset, for a caller (e.g. `invoices_for_user(*, user)`). Views call
  services and selectors; they never build complex queries or hold business rules
  inline.
- **Views:** function-based, not class-based.
- **Audit trail:** `django-simple-history` (`HistoricalRecords` on models that need
  one).
- **Static serving:** WhiteNoise, configured for production static serving.
- **Background work:** **Celery + Redis** (a smaller project may use a lighter
  queue).
- **Dev:** `django-debug-toolbar` (dev-only) — use it or query-count assertions to
  catch N+1 before prod.
