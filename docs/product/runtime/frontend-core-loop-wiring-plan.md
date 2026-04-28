# Nautical Compass — Frontend Wiring Plan for Core Loop

## Purpose
Defines how the frontend should connect to the first 4 live backend endpoints.

This core loop is:

1. Complete Intake
2. Load Results Summary
3. Generate W-9
4. Refresh Helm State

These are already live on the backend.

---

## Live Endpoints

### 1. Complete Intake
- `POST /api/intake/complete`

### 2. Results Summary
- `POST /api/results/summary`

### 3. Generate W-9
- `POST /api/documents/generate-w9`

### 4. Helm State
- `POST /api/helm/state`

---

## Frontend Screens / UI Pieces To Wire

### Intake Screen
Needs:
- Complete Intake button

### Results Screen
Needs:
- loader call for results summary
- display for classification, risk, recommended modules, actions

### Documents Panel
Needs:
- Generate W-9 button
- W-9 success/failure message area
- W-9 review payload display area

### Helm Panel
Needs:
- Helm refresh on intake completion
- Helm refresh after W-9 attempt
- display for:
  - global alert state
  - gauges
  - summary actions

---

## Frontend State To Track

The frontend should keep a shared state object for the current user session.

Suggested shape:

```json
{
  "userId": "demo-user",
  "intakeState": {},
  "scores": {},
  "routes": {},
  "helmState": {},
  "resultsSummary": {},
  "w9ReviewState": {},
  "loading": {
    "completeIntake": false,
    "resultsSummary": false,
    "generateW9": false,
    "helmRefresh": false
  },
  "errors": {
    "completeIntake": "",
    "resultsSummary": "",
    "generateW9": "",
    "helmRefresh": ""
  }
}
Then verify:

```bash id="v7u6hf"
wc -l docs/product/runtime/frontend-core-loop-wiring-plan.md
