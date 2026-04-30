"""
Universal Intake Engine — spine-1-intake-engine
================================================
Routes:
  GET  /intake          — render intake form
  POST /intake          — accept submission, score, store as JSON, redirect to confirmation
  GET  /intake/confirm  — show confirmation with score + missing fields
  GET  /api/intake/status — JSON summary for command-deck status feed

Storage:
  runtime/intake_submissions.jsonl  — one JSON object per line (append-only)
  runtime/intake_latest.json        — overwritten with the most recent submission

Scoring:
  Each required field earns points toward a 0-100 intake_score.
  missing_fields lists any required fields that are blank.
"""

import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/intake", tags=["intake-engine"])
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Storage paths (relative to project root, created at import)
# ---------------------------------------------------------------------------
RUNTIME_DIR = Path("runtime")
RUNTIME_DIR.mkdir(exist_ok=True)

INTAKE_LOG = RUNTIME_DIR / "intake_submissions.jsonl"
INTAKE_LATEST = RUNTIME_DIR / "intake_latest.json"

# ---------------------------------------------------------------------------
# Field definitions + weights
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = [
    ("full_name",      20),
    ("email",          15),
    ("phone",          10),
    ("intake_type",    15),
    ("subject",        20),
    ("description",    20),
]

OPTIONAL_FIELDS = [
    "org_name",
    "preferred_contact",
    "urgency",
    "notes",
]

TOTAL_WEIGHT = sum(w for _, w in REQUIRED_FIELDS)   # 100


# ---------------------------------------------------------------------------
# Scoring helper
# ---------------------------------------------------------------------------
def score_intake(data: dict) -> tuple[int, list[str]]:
    """Return (intake_score 0-100, missing_fields list)."""
    earned = 0
    missing = []
    for field, weight in REQUIRED_FIELDS:
        if (data.get(field) or "").strip():
            earned += weight
        else:
            missing.append(field)
    score = round((earned / TOTAL_WEIGHT) * 100)
    return score, missing


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------
def store_intake(record: dict) -> None:
    """Append to JSONL log and overwrite latest."""
    with INTAKE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    INTAKE_LATEST.write_text(json.dumps(record, indent=2), encoding="utf-8")


def load_latest_intake() -> dict | None:
    if INTAKE_LATEST.exists():
        try:
            return json.loads(INTAKE_LATEST.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def count_submissions() -> int:
    if not INTAKE_LOG.exists():
        return 0
    try:
        return sum(1 for line in INTAKE_LOG.open(encoding="utf-8") if line.strip())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
def intake_get(request: Request):
    return templates.TemplateResponse(request, "intake.html", context={
        "request": request,
        "v": int(time.time()),
    })


@router.post("", response_class=HTMLResponse)
async def intake_post(
    request: Request,
    full_name: str          = Form(""),
    email: str              = Form(""),
    phone: str              = Form(""),
    org_name: str           = Form(""),
    intake_type: str        = Form(""),
    subject: str            = Form(""),
    description: str        = Form(""),
    preferred_contact: str  = Form(""),
    urgency: str            = Form(""),
    notes: str              = Form(""),
):
    intake_id = f"int_{uuid4().hex[:10]}"
    created_at = int(time.time())

    data = {
        "full_name":          full_name.strip(),
        "email":              email.strip(),
        "phone":              phone.strip(),
        "org_name":           org_name.strip(),
        "intake_type":        intake_type.strip(),
        "subject":            subject.strip(),
        "description":        description.strip(),
        "preferred_contact":  preferred_contact.strip(),
        "urgency":            urgency.strip(),
        "notes":              notes.strip(),
    }

    intake_score, missing_fields = score_intake(data)

    record = {
        "intake_id":      intake_id,
        "created_at":     created_at,
        "intake_score":   intake_score,
        "missing_fields": missing_fields,
        "status":         "complete" if not missing_fields else "partial",
        **data,
    }

    store_intake(record)

    return RedirectResponse(f"/intake/confirm?id={intake_id}", status_code=303)


@router.get("/confirm", response_class=HTMLResponse)
def intake_confirm(request: Request, id: str = ""):
    latest = load_latest_intake()
    record = latest if (latest and latest.get("intake_id") == id) else latest
    return templates.TemplateResponse(request, "intake_confirm.html", context={
        "request":  request,
        "record":   record or {},
        "v":        int(time.time()),
    })


# ---------------------------------------------------------------------------
# API — status endpoint for command-deck
# ---------------------------------------------------------------------------

api_router = APIRouter(prefix="/api/intake", tags=["intake-api"])


@api_router.get("/status")
def intake_status():
    latest = load_latest_intake()
    total = count_submissions()
    if latest:
        return JSONResponse({
            "module":           "intake_engine",
            "status":           "active",
            "total_submissions": total,
            "latest_id":        latest.get("intake_id"),
            "latest_score":     latest.get("intake_score"),
            "latest_missing":   latest.get("missing_fields", []),
            "latest_type":      latest.get("intake_type"),
            "latest_status":    latest.get("status"),
            "last_submitted_at": latest.get("created_at"),
        })
    return JSONResponse({
        "module":            "intake_engine",
        "status":            "idle",
        "total_submissions": 0,
        "latest_id":         None,
        "latest_score":      None,
        "latest_missing":    [],
        "latest_type":       None,
        "latest_status":     None,
        "last_submitted_at": None,
    })
