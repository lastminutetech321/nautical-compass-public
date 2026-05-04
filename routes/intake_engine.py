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
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.living_ledger import get_actor_id, log_page_view, log_intake_event

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
def _parse_amount(value: str) -> float:
    try:
        return max(0.0, float(value.strip())) if value.strip() else 0.0
    except ValueError:
        return 0.0


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


def load_intake_by_id(intake_id: str) -> dict | None:
    if not INTAKE_LOG.exists():
        return None
    try:
        with INTAKE_LOG.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("intake_id") == intake_id:
                        return record
                except Exception:
                    continue
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


def load_recent_intakes(limit: int = 10) -> list:
    """Return the most recent `limit` submissions from JSONL, newest first."""
    if not INTAKE_LOG.exists():
        return []
    try:
        lines = [l.strip() for l in INTAKE_LOG.open(encoding="utf-8") if l.strip()]
        records = []
        for line in reversed(lines[-limit:]):
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        return records
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
def intake_get(request: Request, prefill_type: str = Query("")):
    log_page_view(request, rail="system", event_type="intake_form_opened",
                  title="Intake form opened",
                  next_action="intake_submitted",
                  residual_trigger="abandoned_intake_legal_or_labor",
                  extra={"prefill_type": prefill_type} if prefill_type else {})
    return templates.TemplateResponse(request, "intake.html", context={
        "request": request,
        "v": int(time.time()),
        "prefill_type": prefill_type,
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
    # Operator Rail fields
    entity_type: str        = Form(""),
    operator_type_rail: str = Form(""),
    service_area: str       = Form(""),
    formation_state: str    = Form(""),
    ein_status: str         = Form(""),
    w9_status: str          = Form(""),
    insurance_status: str   = Form(""),
    # Labor Rail fields
    role_type: str          = Form(""),
    availability: str       = Form(""),
    skills: str             = Form(""),
    rate_expectation: str   = Form(""),
    labor_location: str     = Form(""),
    union_status: str       = Form(""),
    labor_evidence: List[str] = Form(default=[]),
    # Legal Rail fields
    target_name: str           = Form(""),
    target_type_raw: str       = Form(""),
    target_person: str         = Form(""),
    target_department: str     = Form(""),
    financial_loss_amount: str = Form(""),
    work_loss_amount: str      = Form(""),
    desired_outcome_text: str  = Form(""),
    harm_flags: List[str]      = Form(default=[]),
    prior_complaint_made: str  = Form(""),
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

    if intake_type.strip() == "partner":
        from services.operator_rail_service import build_operator_profile
        rail_data = {
            "entity_type":        entity_type.strip(),
            "operator_type_rail": operator_type_rail.strip(),
            "service_area":       service_area.strip(),
            "formation_state":    formation_state.strip(),
            "ein_status":         ein_status.strip(),
            "w9_status":          w9_status.strip(),
            "insurance_status":   insurance_status.strip(),
        }
        record["operator_rail"] = build_operator_profile(rail_data)

    if intake_type.strip() in ("labor", "production", "worker_profile"):
        from services.labor_rail_service import build_labor_profile
        labor_data = {
            "role_type":       role_type.strip(),
            "availability":    availability.strip(),
            "skills":          skills.strip(),
            "rate_expectation": rate_expectation.strip(),
            "labor_location":  labor_location.strip(),
            "union_status":    union_status.strip(),
            "labor_evidence":  labor_evidence,
        }
        record["labor_rail"] = build_labor_profile(labor_data)

    if intake_type.strip() == "legal":
        from services.standing_analysis_service import analyze_standing
        from services.capacity_analysis_service import analyze_capacity

        raw_ttype = target_type_raw.strip().lower()
        norm_target_type = "government" if ("government" in raw_ttype or "agency" in raw_ttype) else "private"

        harm_set = set(harm_flags)
        complaint = {
            "complaintId":            intake_id,
            "shortTitle":             subject.strip(),
            "plainLanguageSummary":   description.strip(),
            "whatHappened":           description.strip(),
            "targetName":             target_name.strip(),
            "targetType":             norm_target_type,
            "targetPerson":           target_person.strip(),
            "targetDepartment":       target_department.strip(),
            "desiredOutcome":         desired_outcome_text.strip() or notes.strip(),
            "financialLossAmount":    _parse_amount(financial_loss_amount),
            "workLossAmount":         _parse_amount(work_loss_amount),
            "injuryClaimed":          "injury_claimed" in harm_set,
            "propertyDamageClaimed":  "property_damage_claimed" in harm_set,
            "creditImpactClaimed":    "credit_impact_claimed" in harm_set,
            "emotionalStressClaimed": "emotional_stress_claimed" in harm_set,
            "priorComplaintMade":     prior_complaint_made.strip().lower() == "true",
        }
        fake_state: dict = {"complaintProfile": {"complaints": [complaint]}}
        legal_rail: dict = {"target_name": target_name.strip(), "target_type": norm_target_type}

        try:
            sr = analyze_standing(fake_state)
            legal_rail.update({
                "standing":           sr["standing"],
                "standing_label":     sr["standing_label"],
                "injury_met":         sr["injury_in_fact"]["met"],
                "causation_met":      sr["causation"]["met"],
                "redressability_met": sr["redressability"]["met"],
                "concrete_harms":     sr["injury_in_fact"]["concrete_harms"],
                "standing_analysis":  sr["injury_in_fact"]["analysis"],
            })
        except Exception as exc:
            legal_rail.update({
                "standing": False,
                "standing_label": "standing_not_established",
                "standing_error": str(exc),
            })

        try:
            cr = analyze_capacity(fake_state)
            legal_rail.update({
                "capacity_label":          cr["capacity_label"],
                "immunity_risk":           cr["immunity_risk"],
                "recommended_defendants":  cr["recommended_defendants"],
                "immunity_notes":          cr["immunity_notes"],
                "capacity_analysis":       cr["analysis"],
            })
        except Exception as exc:
            legal_rail.update({
                "capacity_label": "unknown",
                "immunity_risk":  "UNKNOWN",
                "capacity_error": str(exc),
            })

        record["legal_rail"] = legal_rail

    store_intake(record)

    log_intake_event(
        request,
        intake_type=intake_type.strip(),
        intake_id=intake_id,
        intake_score=intake_score,
        full_name=full_name.strip(),
    )

    return RedirectResponse(f"/intake/confirm?id={intake_id}", status_code=303)


@router.get("/confirm", response_class=HTMLResponse)
def intake_confirm(request: Request, id: str = ""):
    record = load_intake_by_id(id) if id else load_latest_intake()
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
