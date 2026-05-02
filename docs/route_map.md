# Route Map — Nautical Compass

Last updated: 2026-05-02

## Core App Routes (main.py)

| Method | Path | Handler | Template |
|--------|------|---------|----------|
| GET | / | root | home.html |
| GET | /health | health_check | — (JSON) |
| GET | /checkout | checkout | checkout.html |
| GET | /accessibility | accessibility | accessibility.html |

## Intake Engine (routes/intake_engine.py)

| Method | Path | Notes |
|--------|------|-------|
| GET/POST | /intake/* | Intake flow |
| POST | /api/intake/* | API endpoints |

## Financial Engine (routes/financial_engine_*.py)

| Method | Path | Notes |
|--------|------|-------|
| GET | /financial-engine | Test panel |
| GET | /financial-panel | Panel UI |
| POST | /api/financial/* | Actions |

## Command Deck (command_deck_route.py, command_deck_api.py)

| Method | Path | Notes |
|--------|------|-------|
| GET | /command-deck | Dashboard |
| POST | /api/command-deck/* | API |

## Operator Rail (routes/operator_rail_routes.py) — v1

| Method | Path | Template | Notes |
|--------|------|----------|-------|
| GET | /operator-rail | operator_rail.html | Hub |
| GET | /operator-profile | operator_profile.html | Profile form |
| GET | /captain-preview | captain_preview.html | Capability preview |
| GET | /compliance-checklist | compliance_checklist.html | Readiness checklist |

## Legal Rail (routes/legal_rail_routes.py) — v1

| Method | Path | Service | Notes |
|--------|------|---------|-------|
| POST | /api/legal/standing | standing_analysis_service | Article III injury, causation, redressability |
| POST | /api/legal/capacity | capacity_analysis_service | Official/individual/private capacity routing |
| POST | /api/legal/rights | rights_violation_service | Rights flag detection, §1983, consumer, contract |
| POST | /api/legal/regulatory-routes | regulatory_routing_service | Regulatory forum routing |
| POST | /api/legal/jurisdiction | jurisdiction_service | Jurisdiction track + venue notes |
| POST | /api/legal/results | legal_results_service | Aggregated legal posture (all 5 services) |
| POST | /api/legal/case-packet | case_builder_service | Full assembled case packet |

All endpoints accept `{ intakeState: {...}, complaintId?: "..." }` except `/case-packet` which also requires `userId`.

## Admin (main.py)

| Method | Path | Notes |
|--------|------|-------|
| GET | /admin | Admin hub |
| GET | /admin/* | Sub-admin pages |
