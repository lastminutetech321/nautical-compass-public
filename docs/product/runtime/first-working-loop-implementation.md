# Nautical Compass — First Working Loop Implementation Plan

## Purpose
Defines the first real executable loop for Nautical Compass.

This loop proves the system works end to end:

1. user enters intake data
2. intake saves into schema
3. scores recompute
4. routing recomputes
5. user sees results
6. user clicks Generate W-9
7. W-9 payload is created
8. payload enters review state
9. document history updates
10. Helm refreshes

This is the first operational proof of the NC system.

---

## Loop Scope

### Included in Phase 1
- intake save
- schema write
- score recompute
- upgrade routing recompute
- W-9 payload generation
- review-ready document output
- document history append
- Helm state refresh

### Excluded from Phase 1
- final PDF rendering
- invoice generation
- complaint summary generation
- contractor profile generation
- external API integrations
- payment or checkout logic

---

## Required Files Already Present

### Intake and UI specs
- `docs/product/intake/intake-form-spec.md`
- `docs/product/intake/intake-ui-layout.md`

### Intake and logic files
- `data-model/intake/master-intake-schema.json`
- `data-model/intake/scoring-engine-spec.json`
- `data-model/intake/upgrade-routing-spec.json`
- `data-model/intake/prefill-mapping-spec.json`
- `data-model/intake/w9-generator-spec.json`
- `data-model/intake/evidence-vault-spec.json`

### Runtime and flow specs
- `docs/product/output/w9-output-flow.md`
- `docs/product/runtime/execution-engine.md`
- `docs/product/integration/end-to-end-wiring-plan.md`

---

## Implementation Goal

When a user fills required intake fields and presses **Generate W-9**, the app should:

- validate intake completeness
- compute current system state
- generate a W-9 payload
- show a review state
- mark W-9 as generated in history
- update Helm values

No dead ends.

---

## Code Modules To Build

### 1. Intake State Manager
Purpose:
- receives field updates from UI
- writes updates into intake state object
- supports autosave and section save

Suggested responsibilities:
- `updateField(path, value)`
- `saveSection(sectionId)`
- `getCurrentIntakeState()`

---

### 2. Validation Engine
Purpose:
- validates required fields
- validates generation-critical fields
- returns field-specific errors

Suggested responsibilities:
- `validateField(path, value)`
- `validateSection(sectionId, intakeState)`
- `validateForW9(intakeState)`

---

### 3. Scoring Executor
Purpose:
- reads intake state
- computes score values and labels
- returns updated score object

Suggested responsibilities:
- `computeScores(intakeState)`
- `computeOverallPosition(scores)`

Outputs:
- classificationScore
- savingsOpportunityScore
- riskScore
- complaintStrengthScore
- documentReadinessScore
- entityReadinessScore
- overallPositionLabel

---

### 4. Routing Executor
Purpose:
- reads scores + intake state
- computes modules, routes, and blocked actions

Suggested responsibilities:
- `computeRoutes(intakeState, scores)`

Outputs:
- recommendedModules
- upgradePaths
- priorityActions
- blockedActions
- oneClickRoutes

---

### 5. Prefill Mapper
Purpose:
- maps intake data into output-ready fields
- applies prefill rules for documents

Suggested responsibilities:
- `mapForDocument(documentType, intakeState)`

For Phase 1:
- W-9 only

---

### 6. W-9 Generator
Purpose:
- reads mapped fields
- applies generator rules
- validates generation
- returns review-ready payload

Suggested responsibilities:
- `generateW9Payload(intakeState)`

Output:
- W-9 payload object
- generation status
- missing field list if blocked

---

### 7. Document History Logger
Purpose:
- appends generated document records
- tracks document state changes

Suggested responsibilities:
- `appendDocumentHistory(documentRecord)`
- `markDocumentReady(documentType)`

---

### 8. Helm State Adapter
Purpose:
- reads scores + routes + document state
- produces UI-ready gauge values

Suggested responsibilities:
- `buildHelmState(intakeState, scores, routes, history)`

Outputs:
- Risk Index value
- Flow value
- Signal value
- Direction value
- Velocity value
- System Load value

---

## Suggested Execution Order

### Step 1
Build Intake State Manager

### Step 2
Build Validation Engine

### Step 3
Build Scoring Executor

### Step 4
Build Routing Executor

### Step 5
Build Prefill Mapper for W-9

### Step 6
Build W-9 Generator

### Step 7
Build Document History Logger

### Step 8
Build Helm State Adapter

### Step 9
Wire results screen + Generate W-9 button

---

## Service Flow

### A. On intake field update
1. update intake state
2. validate changed field
3. autosave state
4. optionally recompute partial score state

### B. On section save
1. validate section
2. save state
3. recompute scores
4. recompute routes
5. refresh results summary
6. refresh Helm preview

### C. On intake completion
1. validate full intake
2. compute full scores
3. compute full routes
4. unlock Generate W-9 action
5. show results screen

### D. On Generate W-9
1. validate W-9 requirements
2. build mapped fields
3. generate W-9 payload
4. store document history record
5. set `documentProfile.w9Ready = true`
6. refresh Helm state
7. return review screen payload

---

## Minimal Endpoint / Function Set

### UI-side actions
- `saveIntakeField(path, value)`
- `saveIntakeSection(sectionId)`
- `completeIntake()`
- `generateW9()`
- `getHelmState()`

### Internal execution functions
- `updateField()`
- `validateSection()`
- `computeScores()`
- `computeRoutes()`
- `mapForDocument()`
- `generateW9Payload()`
- `appendDocumentHistory()`
- `buildHelmState()`

---

## Results Screen Requirements

After intake completion, the results screen must show:

- classification summary
- savings opportunity
- risk level
- recommended modules
- Generate W-9 button

The Generate W-9 button should be:
- enabled only when minimum W-9 fields exist
- disabled with clear explanation if blocked

---

## Review Screen Requirements

After W-9 generation, show:

- name line
- business name line
- tax classification
- address
- TIN type
- note that TIN value requires secure entry/review

Buttons:
- Edit intake
- Save draft
- Continue

---

## Error Handling Rules

### Intake errors
- point back to exact section
- do not erase user data

### Score errors
- preserve intake state
- mark score state stale
- allow recompute retry

### W-9 generation errors
- list missing required fields
- keep user in results state
- provide Fix Intake button

### History errors
- do not discard payload
- retry append safely

---

## Success Criteria

Phase 1 succeeds when:

1. user can complete required intake fields
2. system saves intake correctly
3. scores appear on results screen
4. routes appear on results screen
5. Generate W-9 works
6. review state appears
7. document history record is created
8. Helm reflects updated state

---

## Developer Note

Do not jump to polished PDF export yet.

The first milestone is **working payload generation and review flow**.

That proves the system works.

---

## Final Rule

Build the first working loop as one continuous system, not as separate disconnected features.
