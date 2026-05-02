# Module Registry — Nautical Compass

Last updated: 2026-05-02
Branch: overnight-operator-rail-batch
Router: routes/legal_rail_routes.py

## A. Operator Rail Core

| Module | Route | Template | Service | Status |
|--------|-------|----------|---------|--------|
| Operator Rail Hub | /operator-rail | operator_rail.html | — | v1 |
| Operator Profile | /operator-profile | operator_profile.html | — | v1 |
| Captain Preview | /captain-preview | captain_preview.html | — | v1 |
| Compliance Checklist | /compliance-checklist | compliance_checklist.html | compliance_checklist_service.py | v1 |

## B. Legal / Standing / Capacity

| Module | Route | Service | Status |
|--------|-------|---------|--------|
| Standing Analysis | POST /api/legal/standing | standing_analysis_service.py | v1 |
| Capacity Analysis | POST /api/legal/capacity | capacity_analysis_service.py | v1 |
| Rights Violation | POST /api/legal/rights | rights_violation_service.py | v1 |
| Regulatory Routing | POST /api/legal/regulatory-routes | regulatory_routing_service.py | v1 |
| Jurisdiction Analysis | POST /api/legal/jurisdiction | jurisdiction_service.py | v1 |
| Legal Results (all) | POST /api/legal/results | legal_results_service.py | v1 |
| Case Packet Builder | POST /api/legal/case-packet | case_builder_service.py | v1 |

## C. AV Plus Trades

| Module | Route | Status |
|--------|-------|--------|
| AVPT Home | /avpt | active |
| AVPT Client Intake | /avpt/intake | active |
| AVPT Dashboard | /avpt/dashboard | active |

## D. Financial / Payment / Tax Readiness

| Module | Route | Status |
|--------|-------|--------|
| Financial Engine | /financial-engine | active |
| Financial Panel | /financial-panel | active |
| Invoice Service | /api/invoice | active |

## E. Compliance / Renewal / Filing

| Module | Route | Status |
|--------|-------|--------|
| Compliance Checklist | /compliance-checklist | v1 |
| Compliance Service | services/compliance_checklist_service.py | v1 |

## F. Public Growth / Access

| Module | Route | Status |
|--------|-------|--------|
| Home | / | active |
| Checkout | /checkout | active |
| Accessibility | /accessibility | active |

## G. Admin / Audit / Automation

| Module | Route | Status |
|--------|-------|--------|
| Admin Hub | /admin | active |
| Command Deck | /command-deck | active |
| Agent Route Audit | scripts/agent_route_audit.py | active |
| Agent Compile Gate | scripts/agent_compile_gate.py | active |
