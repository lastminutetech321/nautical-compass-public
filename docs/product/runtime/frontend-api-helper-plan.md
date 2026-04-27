# Nautical Compass — Frontend API Helper Plan

## Purpose
Defines the frontend API helper layer for the first proven core loop.

These helpers should be the frontend’s clean interface to the live backend routes.

Core loop helpers:
1. complete intake
2. load results summary
3. generate W-9
4. refresh Helm state

---

## Why This Layer Matters

Do not call fetch logic inline from every button and screen.

Create one frontend API helper layer so:
- request logic stays in one place
- endpoint URLs stay centralized
- error handling stays consistent
- future route swaps are easier
- UI components stay clean

---

## Proven Live Routes

- `POST /api/intake/complete`
- `POST /api/results/summary`
- `POST /api/documents/generate-w9`
- `POST /api/helm/state`

Only build helpers for these first.

---

## Suggested Frontend File

Create something like:

- `static/js/api/coreApi.js`

If your frontend stack differs, adapt path, but keep one dedicated helper file for the core loop.

Possible alternatives:
- `frontend/src/api/coreApi.ts`
- `frontend/src/services/coreApi.ts`
- `static/app/api/coreApi.js`

---

## Recommended Exports

The helper file should export 4 async functions:

- `completeIntake(userId, intakeState)`
- `loadResultsSummary(intakeState)`
- `generateW9(userId, intakeState)`
- `refreshHelmState(intakeState, scores, routes, history)`

Optional shared helper:
- `postJson(url, payload)`

---

## Base Helper Pattern

Use a shared POST helper so every API function behaves the same way.

Conceptual pattern:

```javascript
async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const data = await response.json();

  if (!response.ok || data.ok === false) {
    throw new Error(data.error || data.detail || "Request failed");
  }

  return data.data;
}
Then verify:

```bash id="r6w4pu"
wc -l docs/product/runtime/frontend-api-helper-plan.md
