# Nautical Compass: Current-State Module Audit & Implementation Plan

## 1. Current-State Module Audit

Based on an audit of the repository, the application currently consists of several key domains:
1. **Labor / Production (AV Plus Trades):** Modules for worker intake, production requests, and partner intake.
2. **Labor Signal:** A functional API and dashboard layer for labor market intelligence.
3. **Legal Flow (Nautical Compass):** A multi-step workflow for case intake and remedy drafting.

The Legal Flow is the most clearly scaffolded but unfinished area of the application. It consists of a 4-step sequence:
- **Step 1: Case Dock** - Live intake and document staging (Fully functional with form capture, DB storage, and file upload).
- **Step 2: Signal Dock** - Review layer for deadlines, notices, and risk flags (Currently a static placeholder page).
- **Step 3: Equity Engine** - Remedy layer for requested relief and posture (Currently a static placeholder page).
- **Step 4: Navigator AI / Draft Packet** - Output generation (Navigator AI is in "safe mode" and mostly informational; Draft Packet is functional but relies on Step 1 data bypassing Steps 2 and 3).

**Highest-Value Unfinished Module: Signal Dock**
Signal Dock is the immediate next step after Case Dock in the legal rail. Currently, `signal_dock.html` is entirely static, acting only as a visible review layer. By making it interactive, we bridge the gap between intake (Case Dock) and remedy framing (Equity Engine), allowing users to actually perform the review of deadlines, notices, and risk flags that the module promises.

## 2. Missing Functionality List for Signal Dock

To elevate Signal Dock from a static placeholder to a functional module without downgrading existing architecture:
- **Context Awareness:** The module must load the `case_context` from the database (via `fetch_latest_case()`), similar to `case_update.html` and `draft_packet.html`.
- **Form Data Capture:** It needs a form to capture user inputs for the review layer:
  - Deadlines (filing dates, response windows)
  - Notice Signals (trigger documents received)
  - Risk Flags (contradictions, missing records)
- **Data Persistence:** The submitted data must be saved to the database, updating the existing case record.
- **Workflow Progression:** Successful submission should redirect to a `submission_success.html` screen, then advance the user to the next step (Equity Engine).
- **Fallback State:** If no active case is found, it should prompt the user to start at Case Dock.

## 3. File-by-File Implementation Plan

### File 1: `main.py`
- **Current State:** The `/modules/signal-dock` route only handles GET requests and renders the static template.
- **Planned Changes:**
  1. Update the `GET /modules/signal-dock` route to fetch the latest case using `fetch_latest_case()` and pass it to the template.
  2. Add a new `POST /modules/signal-dock` route to handle form submissions (deadlines, notice signals, risk flags).
  3. In the POST route, append the submitted data to the case's `summary` or a new dedicated field, and use `update_case_record()` to persist the changes.
  4. Return a `submission_success.html` response directing the user to Equity Engine.

### File 2: `templates/signal_dock.html`
- **Current State:** A static HTML page describing the module's purpose with no interactive elements.
- **Planned Changes:**
  1. Add the `legal-rail` progress indicator (Step 2 active).
  2. Wrap the content in conditional logic (`{% if case_context %}`).
  3. Display the current matter title and route for context.
  4. Convert the static feature cards into a `<form class="intake-form">` with `<div class="form-grid">` and `<div class="form-field">` elements matching the existing UI patterns from `case_dock.html`.
  5. Add input fields for:
     - Critical Deadlines (textarea)
     - Notice Signals (textarea)
     - Risk Flags (textarea)
  6. Add a submit button and navigation links using `.module-actions` and `.action-btn`.
  7. Add an `{% else %}` fallback state if no case context is found, prompting a return to Case Dock.

### Constraint Checklist
- [x] Preserve existing architecture (using FastAPI, SQLite, Jinja2).
- [x] Preserve styling direction (reusing existing `.module-box`, `.form-grid`, `.action-btn` CSS classes, even though they are dynamically applied/missing from main CSS, they work in the current template system).
- [x] Do not modify production deployment settings.
- [x] Do not touch live billing credentials.
- [x] Limit changes to `main.py` and `signal_dock.html`.
