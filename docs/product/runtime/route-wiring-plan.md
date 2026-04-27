# Nautical Compass — Route Wiring Plan

## Purpose
Defines the first route/endpoints layer that wires the current runtime, services, and engines into the app.

This plan connects:
- intake actions
- results actions
- document generation
- NC Legal outputs
- Helm payloads

The goal is to make the current system visible and callable from the app.

---

## Wiring Strategy

Wire routes in this order:

1. intake routes
2. results routes
3. document routes
4. NC Legal routes
5. Helm route

Do not wire every future service yet.
Wire only what already exists and works.

---

## Existing Service Layer To Wire

### Intake / results
- `services/intake_service.py`
- `services/results_service.py`
- `services/upgrade_service.py`

### Documents
- `services/document_service.py`
- `services/invoice_service.py`
- `services/contractor_profile_service.py`
- `services/complaint_service.py`
- `services/case_builder_service.py`
- `services/foia_records_service.py`
- `services/notice_demand_service.py`
- `services/affidavit_declaration_service.py`

### NC Legal
- `services/legal_intake_service.py`
- `services/legal_results_service.py`
- `services/guardian_evidence_intake_service.py`
- `services/nc_dashboard_service.py`
- `services/equity_trust_analysis_service.py`

### Helm
- `services/helm_service.py`

---

## Phase 1 Route Set

## 1. Intake Routes

### POST `/intake/save-field`
Purpose:
- save a single intake field
- recompute partial state

Calls:
- `services.intake_service.save_field()`

Request body:
```json id="rb8q7f"
{
  "user_id": "demo-user",
  "field_path": "identityProfile.fullLegalName",
  "value": "Jane Doe",
  "intake_state": {}
}
