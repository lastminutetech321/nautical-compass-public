# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Identity

Three platforms, one codebase:
- **Nautical Compass** — public-facing portal, legal navigation, operator onboarding
- **JurisEngine** — legal routing, standing/capacity analysis, complaint packet generation
- **AV Plus Trades** — labor dispatch, crew matching, AV technician operations

Owned by Apex Vision Holdings LLC. Operating company: CVCS Consulting LLC. Nonprofit arm: AVSTTRA.

## Running the App

```bash
# Activate the project virtualenv (always use this, not system Python)
source .venv/bin/activate

# Run locally (development)
uvicorn main:app --host 0.0.0.0 --port 8000

# Run on a different port (e.g. for branch testing without stopping the live app)
uvicorn main:app --host 0.0.0.0 --port 8001

# Compile-check without running
python3 -m py_compile main.py routes/some_file.py services/some_file.py

# Verify a route is live
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
```

Production runs on DigitalOcean App Platform. Entry point: `web: uvicorn main:app --host 0.0.0.0 --port 8080`. Python 3.11.9.

## Framework

**FastAPI + Jinja2 only.** Never Flask, never Flask Blueprints. All routers are `fastapi.APIRouter`. Templates are rendered via `Jinja2Templates`.

### The `render()` helper (main.py:128)

Most in-`main.py` routes use this helper instead of calling `TemplateResponse` directly:

```python
def render(request: Request, template: str, data=None):
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())          # cache-busting version for static assets
    ctx["labor_signal_flags"] = ...      # feature flags injected on every render
    return templates.TemplateResponse(request, template, context=ctx)
```

Route files that own their own `Jinja2Templates` instance (everything under `routes/`) call `TemplateResponse` directly using the **Starlette 1.0+ signature**: `templates.TemplateResponse(request, "name.html", context={...})`. The old `(name, context_dict)` form is broken in production — never use it.

## Architecture

### Request path

```
HTTP request
  → main.py (mounts static files, SQLite/DB init, top-level routes)
  → APIRouter (routes/*.py, labor_signal/router.py, command_deck_route.py)
  → services/*.py  (pure business logic, no HTTP objects)
  → runtime/*.py   (stateful execution: intake state, scoring, routing, helm)
  → utils/spec_loader.py  (loads JSON specs from data-model/intake/)
```

### Key layers

**`main.py`** (~2600 lines) holds routes that haven't been extracted yet plus app bootstrap. New routes should go into `routes/` files, not main.py. The render helper and db_conn() live here.

**`routes/`** — extracted APIRouters, each with its own `Jinja2Templates` instance:
- `intake_engine.py` — `/intake` flow, append-only JSONL storage in `runtime/`
- `operator_rail_routes.py` — `/operator-rail`, `/operator-profile`, `/captain-preview`, `/compliance-checklist`
- `core_routes.py` — JSON API endpoints (`/api/intake/complete`, `/api/helm-state`, etc.)
- `financial_engine_*.py` — financial panel and actions
- `command_deck_route.py` / `command_deck_api.py` — admin command deck (root-level files, not in routes/)

**`services/`** — stateless business logic. Each file wraps one domain. Call these from routes, never call runtime directly from routes (go through services).

**`runtime/`** — stateful execution layer. `execution_orchestrator.py` is the main entry point; it coordinates `intake_state_manager`, `routing_executor`, `scoring_executor`, `validation_engine`, and `w9_generator`. State is read/written to `runtime/intake_submissions.jsonl` and `runtime/intake_latest.json`.

**`modules/`** — deeper modular subsystems:
- `modules/ledger/` — EventLedger, CareerDNALedger (imported directly in main.py)
- `modules/financial_engine/` — payment providers (Stripe, Mercury, Airwallex), invoice/account models

**`labor_signal/`** — standalone sub-package. Router mounted conditionally at startup under `/modules/labor-signal/*` only when `ENABLE_LABOR_SIGNAL_ENGINE=true`. Has its own config, repository, schemas, and service files.

**`data-model/intake/`** — JSON specification files loaded at runtime by `utils/spec_loader.py`. These drive scoring, routing, validation, and W-9 generation. Do not remove or rename them.

### Database

`db_config.py` is the single source of truth for DB connections. Default: SQLite (`nautical_compass.db`). Postgres activated by setting `DATABASE_URL=postgresql://...`. Most of `main.py` still uses raw `sqlite3.connect(DB_PATH)` directly — `db_config.get_db_connection()` is for new code only. Do not change DB schema without a migration plan.

### Feature flags (environment variables)

```
ENABLE_LABOR_SIGNAL_ENGINE   # true by default; gates entire labor_signal router
ENABLE_OPPORTUNITY_SCORING
ENABLE_SKILL_GAP_ENGINE
ENABLE_MARKET_ROUTING_ADVISORY
SHOW_LABOR_WIDGETS_TO_USERS  # false by default
SHOW_LABOR_WIDGETS_TO_ADMIN  # true by default
USE_SIGNAL_ENGINE_IN_MATCHING

DATABASE_URL                 # postgres:// activates Postgres; unset = SQLite
SQLITE_DB_PATH               # override SQLite file path
TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER  # SMS; graceful no-op if unset
STRIPE_LINK_*                # Stripe checkout link env vars
```

`services/twilio_adapter.py` exposes `is_twilio_configured()` — always check this before calling `send_sms()` so the app never crashes on missing credentials.

## Adding a New Route Module

1. Create `routes/your_module_routes.py` with an `APIRouter` and its own `Jinja2Templates(directory="templates")`.
2. Use `templates.TemplateResponse(request, "your_template.html", context={...})` — request first, name second.
3. Import and wire in `main.py`:
   ```python
   from routes.your_module_routes import your_router
   app.include_router(your_router)
   ```
4. Templates extend `base.html` (`{% extends "base.html" %}`). The `{{ v }}` variable is always available for cache-busting.
5. Compile-check before committing: `python3 -m py_compile main.py routes/your_module_routes.py`.

## Branch and Deployment Rules

- **Never merge to main directly.** Always use a PR branch.
- **Never deploy or merge** without explicit instruction.
- **Never rewrite main.py wholesale** — it's large and fragile; make surgical edits.
- **Never touch** payments, Stripe keys, `.env`, production DB schema, or secrets without explicit approval.
- Hotfixes branch from `origin/main`. Feature branches can branch from `origin/main` or a parent feature branch.
- Work in small commits. Compile-check and curl-test before pushing.
- `scripts/` directory exists but contains no active scripts currently.

## Services Catalog

`services_catalog/catalog.py` defines `SERVICE_GROUPS` — the four top-level service families displayed on `/services`. When adding a new service that should appear on the services page, add its slug/name/description tuple there.

## Known Structural Issues (do not fix without scoping first)

- `main.py` has duplicate `@app.get("/system-status")` and duplicate `@app.post("/legalese")` handlers — the later definitions silently shadow the earlier ones.
- Some deeply nested paths in `modules/financial_engine/models/` are malformed (directory names contain spaces and duplicate path segments) — treat as dead artifacts.
- `labor_signal_flags()` is defined in both `main.py` and `labor_signal/config.py` — the `main.py` version is used for template context injection; the config class version is used within the labor_signal package.
