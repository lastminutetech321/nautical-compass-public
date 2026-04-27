# Nautical Compass — Actual Route Handlers Plan

## Purpose
Defines the concrete route-handler layer to expose current services through the app.

This file answers:
- what route file(s) to create
- what handlers go in them
- what service each handler calls
- what request shape each handler expects
- what response shape each handler returns

---

## Assumption
Keep route handlers thin.

Route handlers should:
1. read request data
2. validate required fields
3. call service
4. return JSON
5. handle errors cleanly

Do not re-implement service logic inside route files.

---

## Recommended Route File Layout

Depending on your current app structure, create or map handlers under something like:

- `routes/intake_routes.py`
- `routes/results_routes.py`
- `routes/document_routes.py`
- `routes/legal_routes.py`
- `routes/dashboard_routes.py`

If the repo uses Flask/FastAPI/Blueprint style, adapt names to match the current app.

---

## Phase 1 — First Visible Loop

Build these handlers first.

### 1. Intake save section
Route:
- `POST /api/intake/save-section`

Handler calls:
- `services.intake_service.save_section`

Required request body:
```json
{
  "userId": "demo-user",
  "sectionId": "identity",
  "payload": {
    "identityProfile.fullLegalName": "Jane Doe",
    "identityProfile.email": "jane@example.com"
  },
  "intakeState": {}
touch docs/product/runtime/actual-route-handlers-plan.md
cat > docs/product/runtime/actual-route-handlers-plan.md <<'EOF'
# Nautical Compass — Actual Route Handlers Plan

## Purpose
Defines the concrete route-handler layer to expose current services through the app.

This file answers:
- what route file(s) to create
- what handlers go in them
- what service each handler calls
- what request shape each handler expects
- what response shape each handler returns

---

## Assumption
Keep route handlers thin.

Route handlers should:
1. read request data
2. validate required fields
3. call service
4. return JSON
5. handle errors cleanly

Do not re-implement service logic inside route files.

---

## Recommended Route File Layout

Depending on your current app structure, create or map handlers under something like:

- `routes/intake_routes.py`
- `routes/results_routes.py`
- `routes/document_routes.py`
- `routes/legal_routes.py`
- `routes/dashboard_routes.py`

If the repo uses Flask/FastAPI/Blueprint style, adapt names to match the current app.

---

## Phase 1 — First Visible Loop

Build these handlers first.

### 1. Intake save section
Route:
- `POST /api/intake/save-section`

Handler calls:
- `services.intake_service.save_section`

Required request body:
```json
{
  "userId": "demo-user",
  "sectionId": "identity",
  "payload": {
    "identityProfile.fullLegalName": "Jane Doe",
    "identityProfile.email": "jane@example.com"
  },
  "intakeState": {}
}
touch docs/product/runtime/first-route-file-plan.md
cat > docs/product/runtime/first-route-file-plan.md <<'EOF'
# Nautical Compass — First Route File Plan

## Purpose
Defines the first actual route file to build so the app can expose one visible working loop.

This first file should focus on:
- intake complete
- results summary
- W-9 generation
- Helm state

Do not start with every route.
Start with the shortest visible loop.

---

## Recommended First Route File

Create:

- `routes/core_routes.py`

Why:
Because the first visible loop crosses multiple service groups:
- intake
- results
- documents
- Helm

So one starter route file is cleaner than splitting too early.

Later, this can be broken into:
- `intake_routes.py`
- `results_routes.py`
- `document_routes.py`
- `dashboard_routes.py`

But for the first pass:
- one route file
- one visible loop
- less friction

---

## First Routes To Add

### 1. `POST /api/intake/complete`
Calls:
- `services.intake_service.complete_intake`

Purpose:
- completes intake
- computes scores
- computes routes
- updates Helm state
- returns results-ready payload

---

### 2. `GET /api/results/summary`
Calls:
- `services.results_service.build_results_summary`

Purpose:
- returns results panel data
- returns score summaries
- returns recommended modules
- returns priority actions

---

### 3. `POST /api/documents/generate-w9`
Calls:
- `services.document_service.generate_w9`

Purpose:
- generates W-9 review payload
- updates intake state
- appends history
- updates Helm

---

### 4. `GET /api/helm/state`
Calls:
- `services.helm_service.get_helm_state`

Purpose:
- returns live Helm state
- gives app a dashboard/status payload

---

## Why These 4 First

Because together they create the first real app loop:

1. user completes intake
2. app shows results
3. user clicks generate W-9
4. app refreshes Helm

That is the first loop worth exposing visibly.

---

## Expected File Responsibilities

`routes/core_routes.py` should:

- import framework router objects
- import 4 service functions
- define 4 handlers
- validate request data
- return clean JSON responses
- keep logic thin

It should **not**:
- compute business logic directly
- reimplement scoring
- reimplement document logic
- reimplement Helm logic

---

## Expected Imports

At minimum, route file will likely need:

- request/json response object from current framework
- `complete_intake`
- `build_results_summary`
- `generate_w9`
- `get_helm_state`

Possible shape:

```python
from services.intake_service import complete_intake
from services.results_service import build_results_summary
from services.document_service import generate_w9
from services.helm_service import get_helm_state
touch docs/product/runtime/core-routes-plan.md
cat > docs/product/runtime/core-routes-plan.md <<'EOF'
# Nautical Compass — core_routes.py Plan

## Purpose
Defines the first real route file to expose the first visible working loop inside the app.

Target loop:
1. complete intake
2. load results
3. generate W-9
4. refresh Helm

This file is a build plan for:

- `routes/core_routes.py`

---

## Goal
Create one starter route file that wires existing services into app-callable endpoints.

Do not split into multiple route files yet.

Keep first implementation simple:
- one route file
- four handlers
- one visible loop
- thin route logic

---

## File To Create

- `routes/core_routes.py`

If the repo already has a routes folder or framework-specific location, adapt the exact path, but keep the same handler set.

---

## Services This File Will Use

### Intake
- `services.intake_service.complete_intake`

### Results
- `services.results_service.build_results_summary`

### Documents
- `services.document_service.generate_w9`

### Helm
- `services.helm_service.get_helm_state`

---

## Routes In This File

### 1. POST `/api/intake/complete`
Purpose:
- complete intake
- compute results-ready state
- return scores/routes/Helm data

Handler calls:
- `complete_intake(user_id, intake_state)`

---

### 2. GET `/api/results/summary`
Purpose:
- return results payload for current intake state

Handler calls:
- `build_results_summary(intake_state)`

---

### 3. POST `/api/documents/generate-w9`
Purpose:
- generate W-9 review payload
- return updated intake/document/Helm state

Handler calls:
- `generate_w9(user_id, intake_state)`

---

### 4. GET `/api/helm/state`
Purpose:
- return current Helm payload

Handler calls:
- `get_helm_state(...)`

---

## Expected Route File Shape

The file should contain:

1. framework imports
2. service imports
3. router / blueprint creation
4. helper for success response
5. helper for error response
6. 4 route handlers

---

## Suggested Handler Names

- `post_complete_intake()`
- `get_results_summary()`
- `post_generate_w9()`
- `get_helm_state_route()`

Use clearer names if the framework requires uniqueness.

---

## Framework-Agnostic Flow

### Complete intake handler
1. read JSON body
2. pull `userId`
3. pull `intakeState`
4. validate both
5. call `complete_intake`
6. return `{ "ok": true, "data": result }`

---

### Results summary handler
1. read intake state from request or store
2. validate intake state
3. call `build_results_summary`
4. return `{ "ok": true, "data": result }`

---

### Generate W-9 handler
1. read JSON body
2. pull `userId`
3. pull `intakeState`
4. validate both
5. call `generate_w9`
6. return `{ "ok": true, "data": result }`

---

### Helm state handler
1. read current intake state or body
2. validate required inputs
3. call `get_helm_state`
4. return `{ "ok": true, "data": result }`

---

## Required Request Shapes

### POST `/api/intake/complete`
```json id="9s6g3f"
{
  "userId": "demo-user",
  "intakeState": {}
}
Then verify:

```bash id="wyrr9f"
wc -l docs/product/runtime/core-routes-plan.md
mkdir -p routes && cat > routes/core_routes.py <<'EOF'
from flask import Blueprint, jsonify, request

from services.intake_service import complete_intake
from services.results_service import build_results_summary
from services.document_service import generate_w9
from services.helm_service import get_helm_state


core_routes = Blueprint("core_routes", __name__)


def success(data, status_code=200):
    return jsonify({"ok": True, "data": data}), status_code


def failure(message, status_code=400):
    return jsonify({"ok": False, "error": message}), status_code


@core_routes.route("/api/intake/complete", methods=["POST"])
def post_complete_intake():
    try:
        body = request.get_json(silent=True) or {}

        user_id = body.get("userId")
        intake_state = body.get("intakeState")

        if not user_id:
            return failure("userId is required", 400)
        if intake_state is None:
            return failure("intakeState is required", 400)

        result = complete_intake(user_id, intake_state)
        return success(result)

    except Exception as exc:
        return failure(str(exc), 500)


@core_routes.route("/api/results/summary", methods=["POST"])
def post_results_summary():
    try:
        body = request.get_json(silent=True) or {}
        intake_state = body.get("intakeState")

        if intake_state is None:
            return failure("intakeState is required", 400)

        result = build_results_summary(intake_state)
        return success(result)

    except Exception as exc:
        return failure(str(exc), 500)


@core_routes.route("/api/documents/generate-w9", methods=["POST"])
def post_generate_w9():
    try:
        body = request.get_json(silent=True) or {}

        user_id = body.get("userId")
        intake_state = body.get("intakeState")

        if not user_id:
            return failure("userId is required", 400)
        if intake_state is None:
            return failure("intakeState is required", 400)

        result = generate_w9(user_id, intake_state)
        return success(result)

    except Exception as exc:
        return failure(str(exc), 500)


@core_routes.route("/api/helm/state", methods=["POST"])
def post_helm_state():
    try:
        body = request.get_json(silent=True) or {}

        intake_state = body.get("intakeState")
        scores = body.get("scores", {})
        routes = body.get("routes", {})
        history = body.get("history", [])

        if intake_state is None:
            return failure("intakeState is required", 400)

        result = get_helm_state(
            intake_state=intake_state,
            scores=scores,
            routes=routes,
            history=history,
        )
        return success(result)

    except Exception as exc:
        return failure(str(exc), 500)


if __name__ == "__main__":
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(core_routes)

    @app.route("/")
    def index():
        return jsonify({"ok": True, "message": "core_routes loaded"})

    app.run(host="0.0.0.0", port=5001, debug=True)
