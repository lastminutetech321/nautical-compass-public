# Operator Rail Architecture

## Purpose

The Operator Rail guides workers, AV techs, freelancers, and contractors from worker status into structured operator status. It is a compliance-first onboarding and readiness pathway.

## Route Structure

```
/operator-rail          — Hub: entry point, mission statement, path options
/operator-profile       — Operator identity, business type, trade classification
/captain-preview        — Preview of operator capabilities and platform access
/compliance-checklist   — Readiness checklist: licenses, filings, structure
```

## Data Flow

```
/operator-rail
    └─► /operator-profile  (operator enters their info)
            └─► /compliance-checklist  (system checks readiness)
                    └─► /captain-preview  (unlocks preview if ready)
```

## Service Layer

`services/compliance_checklist_service.py`
- `get_checklist_items(operator_type)` — returns list of checklist items keyed by operator type
- `score_checklist(responses)` — returns readiness score and gap list

## Router

`routes/operator_rail_routes.py`
- FastAPI APIRouter, prefix none (top-level routes)
- Jinja2 TemplateResponse for all four routes
- Uses shared `templates` instance passed at app level

## Templates

All four templates extend `base.html` via `{% extends "base.html" %}`.

| Template | Purpose |
|----------|---------|
| operator_rail.html | Hub landing page |
| operator_profile.html | Profile form |
| captain_preview.html | Capability preview |
| compliance_checklist.html | Interactive checklist |

## Operator Types Supported (v1)

- `freelancer` — independent contractor, 1099 worker
- `av_tech` — audiovisual technician / trades worker
- `sole_proprietor` — sole proprietor business
- `llc` — single-member or multi-member LLC

## Compliance Domains (v1)

1. Business structure (EIN, LLC formation, DBA registration)
2. Tax readiness (W-9, quarterly estimates, bookkeeping)
3. Licensing & permits (trade license, local business license)
4. Insurance (general liability, professional liability)
5. Contracts (standard client agreement, scope-of-work template)
