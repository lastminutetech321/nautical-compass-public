# Nautical Compass — End-to-End Wiring Plan

## Purpose
Defines how Nautical Compass connects the full system from intake to outputs, routing, Helm, and document history.

This is the integration layer between:
- intake UI
- intake schema
- scoring
- prefill
- document generation
- Helm
- upgrade routing

---

## Core Flow

1. User starts intake
2. Intake UI writes field values into master intake schema
3. System validates required fields section by section
4. System saves progress
5. System recomputes scores
6. System recomputes upgrade routing
7. System enables available document outputs
8. System updates Helm state
9. System appends generated documents to history
10. User reviews outputs and continues

---

## Primary System Chain

```text
Intake UI
→ intake-form-spec.md
→ master-intake-schema.json
→ scoring-engine-spec.json
→ upgrade-routing-spec.json
→ prefill-mapping-spec.json
→ w9-generator-spec.json
→ w9-output-flow.md
→ evidence-vault-spec.json
→ Helm
Then verify:

```bash
wc -l docs/product/integration/end-to-end-wiring-plan.md
