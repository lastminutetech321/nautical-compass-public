# =========================
# main.py — MODULE 1
# Imports, app setup, folders, DB init
# =========================

from pathlib import Path
import json
import shutil
import sqlite3
import time
from uuid import uuid4

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Nautical Compass")

UPLOAD_ROOT = Path("uploads")
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="uploads")

templates = Jinja2Templates(directory="templates")

DB_PATH = Path("nautical_compass.db")

CASE_DOCK_UPLOADS = UPLOAD_ROOT / "case_dock"
PRODUCTION_UPLOADS = UPLOAD_ROOT / "production"
LABOR_UPLOADS = UPLOAD_ROOT / "labor"
PARTNER_UPLOADS = UPLOAD_ROOT / "partner"
CASE_FILES_ROOT = UPLOAD_ROOT / "cases"

for folder in [
    CASE_DOCK_UPLOADS,
    PRODUCTION_UPLOADS,
    LABOR_UPLOADS,
    PARTNER_UPLOADS,
    CASE_FILES_ROOT,
]:
    folder.mkdir(parents=True, exist_ok=True)

PRODUCTION_SUBMISSIONS = []
LABOR_SUBMISSIONS = []
PARTNER_SUBMISSIONS = []


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_title TEXT,
                jurisdiction TEXT,
                issue_type TEXT,
                parties TEXT,
                timeline TEXT,
                summary TEXT,
                requested_outcome TEXT,
                created_at INTEGER,
                case_folder_name TEXT,
                route_name TEXT,
                route_json TEXT,
                files_json TEXT,
                generated_docs_json TEXT
            )
            """
        )
        conn.commit()


init_db()

# =========================
# main.py — MODULE 2A
# Render helper + upload saving
# =========================

def render(request: Request, template: str, data=None):
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return templates.TemplateResponse(template, ctx)


def save_uploads(files: list[UploadFile], target_dir: Path) -> list[dict]:
    saved_files = []

    for file in files:
        if not file or not file.filename:
            continue

        safe_name = f"{int(time.time())}_{uuid4().hex}_{file.filename}"
        out_path = target_dir / safe_name

        with out_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        saved_files.append(
            {
                "name": file.filename,
                "stored_name": safe_name,
                "path": str(out_path),
                "url": f"/uploads/{out_path.relative_to(UPLOAD_ROOT).as_posix()}",
            }
        )

    return saved_files

# =========================
# main.py — MODULE 2B
# Case route inference
# =========================

def infer_case_route(case_data: dict) -> dict:
    text = " ".join(
        [
            case_data.get("matter_title", ""),
            case_data.get("issue_type", ""),
            case_data.get("summary", ""),
            case_data.get("requested_outcome", ""),
            case_data.get("timeline", ""),
        ]
    ).lower()

    route_name = "General Civil / Administrative Review"
    rationale = [
        "The intake does not point to a single narrow route yet, so the matter remains in broad review posture.",
        "The system should preserve the record, identify timing issues, and prepare an action path before deeper drafting.",
    ]
    next_actions = [
        "Refine the timeline and isolate the triggering event.",
        "List every notice, denial, correspondence, and deadline in order.",
        "Prepare a first-pass demand or complaint outline from the existing file.",
    ]
    document_set = [
        "Case Summary Memorandum",
        "Evidence Index",
        "Next-Step Action Brief",
        "Complaint / Demand Outline",
    ]

    if any(word in text for word in ["fcra", "credit report", "consumer report", "transunion", "equifax", "experian"]):
        route_name = "FCRA / Consumer Reporting Route"
        rationale = [
            "The intake points to inaccurate reporting, reinvestigation failure, or consumer-report harm.",
            "This route benefits from a dispute chronology, proof of inaccuracy, and a damages or correction strategy.",
        ]
        next_actions = [
            "Verify dispute dates, reinvestigation dates, and each bureau or furnisher involved.",
            "Prepare a dispute chronology and preserve all written notices and report copies.",
            "Generate a demand letter and complaint outline focused on reporting inaccuracies and resulting harm.",
        ]
        document_set = [
            "FCRA Case Summary",
            "Dispute Chronology",
            "Demand Letter Draft",
            "Complaint Outline",
        ]

    elif any(word in text for word in ["eviction", "landlord", "tenant", "lease", "housing"]):
        route_name = "Housing / Tenant Defense Route"
        rationale = [
            "The matter appears tied to housing, lease terms, landlord conduct, or removal risk.",
            "Housing matters are deadline sensitive and benefit from immediate chronology and document control.",
        ]
        next_actions = [
            "Pin down hearing dates, notice dates, payment history, and lease language.",
            "Preserve every notice to quit, late notice, inspection note, and payment record.",
            "Prepare a defense outline and document packet for immediate review.",
        ]
        document_set = [
            "Housing Defense Summary",
            "Timeline and Notice Index",
            "Defense Outline",
            "Document Packet Checklist",
        ]

    elif any(word in text for word in ["employment", "termination", "discrimination", "retaliation", "eeoc", "workplace"]):
        route_name = "Employment / EEOC Route"
        rationale = [
            "The intake suggests an employment-related conflict, adverse action, or discrimination problem.",
            "These matters benefit from chronology, comparator facts, preserved communications, and agency timing awareness.",
        ]
        next_actions = [
            "List every adverse action, supervisor communication, and date in sequence.",
            "Preserve performance reviews, emails, texts, writeups, and notices.",
            "Prepare an administrative filing outline and a supporting evidence index.",
        ]
        document_set = [
            "Employment Matter Summary",
            "Adverse Action Timeline",
            "Administrative Filing Outline",
            "Evidence Index",
        ]

    elif any(word in text for word in ["contract", "breach", "agreement", "invoice", "payment", "vendor"]):
        route_name = "Contract / Payment Enforcement Route"
        rationale = [
            "The intake appears to involve an agreement, nonpayment, performance dispute, or broken obligation.",
            "This route depends on contract terms, breach dates, notice opportunities, and remedy framing.",
        ]
        next_actions = [
            "Identify the contract, parties, scope, breach point, and notice provisions.",
            "Preserve invoices, payment records, communications, and performance evidence.",
            "Prepare a breach summary and demand letter draft.",
        ]
        document_set = [
            "Contract Dispute Summary",
            "Breach Timeline",
            "Demand Letter Draft",
            "Complaint Outline",
        ]

    return {
        "route_name": route_name,
        "rationale": rationale,
        "next_actions": next_actions,
        "document_set": document_set,
    }

# =========================
# main.py — MODULE 3A
# Case folder writing
# =========================

def write_case_folder(case_data: dict, files: list[dict], route_data: dict) -> tuple[str, list[dict]]:
    case_folder_name = f"case_{case_data['id']}_{uuid4().hex[:8]}"
    case_folder = CASE_FILES_ROOT / case_folder_name
    case_folder.mkdir(parents=True, exist_ok=True)

    metadata = {
        "case_id": case_data["id"],
        "matter_title": case_data["matter_title"],
        "jurisdiction": case_data["jurisdiction"],
        "issue_type": case_data["issue_type"],
        "requested_outcome": case_data["requested_outcome"],
        "parties": case_data["parties"],
        "timeline": case_data["timeline"],
        "summary": case_data["summary"],
        "files": files,
        "route": route_data,
        "created_at": case_data["created_at"],
    }

    with (case_folder / "case_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    generated_docs = []

    case_summary_text = f"""CASE SUMMARY MEMORANDUM

Case ID: {case_data["id"]}
Matter Title: {case_data["matter_title"]}
Jurisdiction: {case_data["jurisdiction"]}
Issue Type: {case_data["issue_type"]}
Requested Outcome: {case_data["requested_outcome"]}

PARTIES
{case_data["parties"]}

TIMELINE
{case_data["timeline"]}

SUMMARY
{case_data["summary"]}

RECOMMENDED ROUTE
{route_data["route_name"]}

RATIONALE
- {route_data["rationale"][0]}
- {route_data["rationale"][1]}
"""
    summary_file = case_folder / "case_summary_memorandum.txt"
    summary_file.write_text(case_summary_text, encoding="utf-8")
    generated_docs.append(
        {
            "title": "Case Summary Memorandum",
            "url": f"/uploads/{summary_file.relative_to(UPLOAD_ROOT).as_posix()}",
        }
    )

    evidence_text = f"""EVIDENCE INDEX

Case ID: {case_data["id"]}
Matter Title: {case_data["matter_title"]}

FILES RECEIVED
"""
    if files:
        for item in files:
            evidence_text += f"- {item['name']}\n"
    else:
        evidence_text += "- No files uploaded.\n"

    evidence_file = case_folder / "evidence_index.txt"
    evidence_file.write_text(evidence_text, encoding="utf-8")
    generated_docs.append(
        {
            "title": "Evidence Index",
            "url": f"/uploads/{evidence_file.relative_to(UPLOAD_ROOT).as_posix()}",
        }
    )

    action_text = f"""NEXT-STEP ACTION BRIEF

Case ID: {case_data["id"]}
Recommended Route: {route_data["route_name"]}

RATIONALE
- {route_data["rationale"][0]}
- {route_data["rationale"][1]}

RECOMMENDED NEXT ACTIONS
"""
    for action in route_data["next_actions"]:
        action_text += f"- {action}\n"

    action_text += "\nAUTO-GENERATED DOCUMENT SET\n"
    for doc in route_data["document_set"]:
        action_text += f"- {doc}\n"

    action_file = case_folder / "next_step_action_brief.txt"
    action_file.write_text(action_text, encoding="utf-8")
    generated_docs.append(
        {
            "title": "Next-Step Action Brief",
            "url": f"/uploads/{action_file.relative_to(UPLOAD_ROOT).as_posix()}",
        }
    )

    complaint_outline_text = f"""COMPLAINT / DEMAND OUTLINE

Case ID: {case_data["id"]}
Matter Title: {case_data["matter_title"]}

1. Parties
2. Jurisdiction / Venue
3. Relevant Facts
4. Chronology of Events
5. Harm / Injury
6. Claims / Theories To Explore
7. Requested Relief
8. Supporting Documents
9. Next Filing / Demand Route

Initial Route Category:
{route_data["route_name"]}
"""
    complaint_file = case_folder / "complaint_or_demand_outline.txt"
    complaint_file.write_text(complaint_outline_text, encoding="utf-8")
    generated_docs.append(
        {
            "title": "Complaint / Demand Outline",
            "url": f"/uploads/{complaint_file.relative_to(UPLOAD_ROOT).as_posix()}",
        }
    )

    return case_folder_name, generated_docs

# =========================
# main.py — MODULE 3B
# DB storage + latest case fetch
# =========================

def store_case_record(case_data: dict):
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO cases (
                id,
                matter_title,
                jurisdiction,
                issue_type,
                parties,
                timeline,
                summary,
                requested_outcome,
                created_at,
                case_folder_name,
                route_name,
                route_json,
                files_json,
                generated_docs_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_data["id"],
                case_data["matter_title"],
                case_data["jurisdiction"],
                case_data["issue_type"],
                case_data["parties"],
                case_data["timeline"],
                case_data["summary"],
                case_data["requested_outcome"],
                case_data["created_at"],
                case_data["case_folder_name"],
                case_data["route"]["route_name"],
                json.dumps(case_data["route"]),
                json.dumps(case_data["files"]),
                json.dumps(case_data["generated_docs"]),
            ),
        )
        conn.commit()


def fetch_latest_case():
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM cases ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not row:
        return None

    return {
        "id": row["id"],
        "matter_title": row["matter_title"],
        "jurisdiction": row["jurisdiction"],
        "issue_type": row["issue_type"],
        "parties": row["parties"],
        "timeline": row["timeline"],
        "summary": row["summary"],
        "requested_outcome": row["requested_outcome"],
        "created_at": row["created_at"],
        "case_folder_name": row["case_folder_name"],
        "route": json.loads(row["route_json"]) if row["route_json"] else {},
        "files": json.loads(row["files_json"]) if row["files_json"] else [],
        "generated_docs": json.loads(row["generated_docs_json"]) if row["generated_docs_json"] else [],
    }

# =========================
# main.py — MODULE 4A
# Core page routes
# =========================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "index.html")


@app.get("/hall", response_class=HTMLResponse)
def hall(request: Request):
    return render(request, "hall.html")


@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return render(request, "services.html")


@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    return render(request, "dashboards_hub.html")


@app.get("/lead", response_class=HTMLResponse)
def lead(request: Request):
    return render(request, "lead_intake.html")


@app.post("/lead")
def lead_submit(
    name: str = Form(""),
    email: str = Form(""),
    message: str = Form("")
):
    return RedirectResponse("/lead/thanks", status_code=303)


@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return render(request, "lead_thanks.html")


@app.get("/sponsor", response_class=HTMLResponse)
def sponsor(request: Request):
    return render(request, "sponsor.html")


@app.get("/checkout")
def checkout():
    return JSONResponse({"ok": True, "message": "Checkout placeholder active."})

# =========================
# main.py — MODULE 4B
# Partner, production, labor routes
# =========================

@app.get("/partner", response_class=HTMLResponse)
def partner(request: Request):
    return render(request, "partner_intake.html")


@app.post("/partner")
async def partner_submit(
    request: Request,
    company_name: str = Form(""),
    contact_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    category: str = Form(""),
    territory: str = Form(""),
    capabilities: str = Form(""),
    notes: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    saved_files = save_uploads(files, PARTNER_UPLOADS)
    submission_id = len(PARTNER_SUBMISSIONS) + 1

    PARTNER_SUBMISSIONS.append(
        {
            "id": submission_id,
            "company_name": company_name,
            "contact_name": contact_name,
            "email": email,
            "phone": phone,
            "category": category,
            "territory": territory,
            "capabilities": capabilities,
            "notes": notes,
            "files": saved_files,
            "created_at": int(time.time()),
        }
    )

    return render(
        request,
        "submission_success.html",
        {
            "title": "Partner Port Submission Received",
            "summary": "Your partner or manufacturer intake has been captured and routed into the system.",
            "return_href": "/services",
            "return_label": "Back to Service Ports",
            "next_href": "/dashboards",
            "next_label": "Open Operations Deck",
            "record_id": submission_id,
            "file_count": len(saved_files),
            "step_number": 1,
            "step_total": 1,
            "step_name": "Partner Port",
            "why_next": "Your partner record is captured. The next useful place is the Operations Deck so you can review where this lane sits in the wider system.",
        },
    )


@app.get("/intake/production", response_class=HTMLResponse)
def intake_production(request: Request):
    return render(request, "intake_production.html")


@app.post("/intake/production")
async def intake_production_submit(
    request: Request,
    company_name: str = Form(""),
    contact_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    event_name: str = Form(""),
    event_type: str = Form(""),
    event_location: str = Form(""),
    event_dates: str = Form(""),
    crew_needed: str = Form(""),
    logistics_notes: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    saved_files = save_uploads(files, PRODUCTION_UPLOADS)
    submission_id = len(PRODUCTION_SUBMISSIONS) + 1

    PRODUCTION_SUBMISSIONS.append(
        {
            "id": submission_id,
            "company_name": company_name,
            "contact_name": contact_name,
            "email": email,
            "phone": phone,
            "event_name": event_name,
            "event_type": event_type,
            "event_location": event_location,
            "event_dates": event_dates,
            "crew_needed": crew_needed,
            "logistics_notes": logistics_notes,
            "files": saved_files,
            "created_at": int(time.time()),
        }
    )

    return render(
        request,
        "submission_success.html",
        {
            "title": "Production Request Received",
            "summary": "The production command intake has been captured for crew and logistics routing.",
            "return_href": "/services",
            "return_label": "Back to Service Ports",
            "next_href": "/intake/labor",
            "next_label": "Continue to Labor Dispatch",
            "record_id": submission_id,
            "file_count": len(saved_files),
            "step_number": 1,
            "step_total": 3,
            "step_name": "Production Command",
            "why_next": "Production needs to connect to workforce supply. Labor Dispatch is the next lane where worker-side readiness and role coverage can be aligned.",
        },
    )


@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor(request: Request):
    return render(request, "intake_labor.html")


@app.post("/intake/labor")
async def intake_labor_submit(
    request: Request,
    full_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    primary_role: str = Form(""),
    certifications: str = Form(""),
    market_area: str = Form(""),
    availability: str = Form(""),
    transport: str = Form(""),
    notes: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    saved_files = save_uploads(files, LABOR_UPLOADS)
    submission_id = len(LABOR_SUBMISSIONS) + 1

    LABOR_SUBMISSIONS.append(
        {
            "id": submission_id,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "primary_role": primary_role,
            "certifications": certifications,
            "market_area": market_area,
            "availability": availability,
            "transport": transport,
            "notes": notes,
            "files": saved_files,
            "created_at": int(time.time()),
        }
    )

    return render(
        request,
        "submission_success.html",
        {
            "title": "Labor Dispatch Intake Received",
            "summary": "Your workforce profile has been captured for dispatch readiness and route matching.",
            "return_href": "/services",
            "return_label": "Back to Service Ports",
            "next_href": "/dashboards",
            "next_label": "Open Operations Deck",
            "record_id": submission_id,
            "file_count": len(saved_files),
            "step_number": 2,
            "step_total": 3,
            "step_name": "Labor Dispatch",
            "why_next": "The worker profile is now staged. The deck is the best place to monitor how operator and client lanes will connect as the system deepens.",
        },
    )

# =========================
# main.py — MODULE 5A
# Legal module routes: Case Dock + submit
# =========================

@app.get("/modules/case-dock", response_class=HTMLResponse)
def case_dock(request: Request):
    return render(request, "case_dock.html")


@app.post("/modules/case-dock")
async def case_dock_submit(
    request: Request,
    matter_title: str = Form(""),
    jurisdiction: str = Form(""),
    issue_type: str = Form(""),
    parties: str = Form(""),
    timeline: str = Form(""),
    summary: str = Form(""),
    requested_outcome: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    with db_conn() as conn:
        next_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM cases"
        ).fetchone()[0]

    saved_files = save_uploads(files, CASE_DOCK_UPLOADS)

    case_data = {
        "id": next_id,
        "matter_title": matter_title,
        "jurisdiction": jurisdiction,
        "issue_type": issue_type,
        "parties": parties,
        "timeline": timeline,
        "summary": summary,
        "requested_outcome": requested_outcome,
        "files": saved_files,
        "created_at": int(time.time()),
    }

    route_data = infer_case_route(case_data)
    case_folder_name, generated_docs = write_case_folder(case_data, saved_files, route_data)

    case_data["route"] = route_data
    case_data["case_folder_name"] = case_folder_name
    case_data["generated_docs"] = generated_docs

    store_case_record(case_data)

    return render(
        request,
        "submission_success.html",
        {
            "title": "Case Dock Intake Received",
            "summary": "Your case intake and supporting documents have been captured and staged for the next legal route.",
            "return_href": "/services",
            "return_label": "Back to Service Ports",
            "next_href": "/modules/signal-dock",
            "next_label": "Continue to Signal Dock",
            "record_id": next_id,
            "file_count": len(saved_files),
            "step_number": 1,
            "step_total": 4,
            "step_name": "Case Dock",
            "why_next": "Case Dock gathers the facts and files. Signal Dock is next because it reviews deadlines, notices, triggers, and risk signals before remedy analysis.",
        },
    )

# =========================
# main.py — MODULE 5B
# Legal intake + legal module routes
# =========================

@app.get("/modules/case-dock", response_class=HTMLResponse)
def case_dock(request: Request):
    return render(request, "case_dock.html")


@app.post("/modules/case-dock")
async def case_dock_submit(
    request: Request,
    matter_title: str = Form(""),
    jurisdiction: str = Form(""),
    issue_type: str = Form(""),
    parties: str = Form(""),
    timeline: str = Form(""),
    summary: str = Form(""),
    requested_outcome: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    with db_conn() as conn:
        next_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM cases"
        ).fetchone()[0]

    saved_files = save_uploads(files, CASE_DOCK_UPLOADS)

    case_data = {
        "id": next_id,
        "matter_title": matter_title,
        "jurisdiction": jurisdiction,
        "issue_type": issue_type,
        "parties": parties,
        "timeline": timeline,
        "summary": summary,
        "requested_outcome": requested_outcome,
        "files": saved_files,
        "created_at": int(time.time()),
    }

    route_data = infer_case_route(case_data)
    case_folder_name, generated_docs = write_case_folder(
        case_data,
        saved_files,
        route_data,
    )

    case_data["route"] = route_data
    case_data["case_folder_name"] = case_folder_name
    case_data["generated_docs"] = generated_docs

    store_case_record(case_data)

    return render(
        request,
        "submission_success.html",
        {
            "title": "Case Dock Intake Received",
            "summary": "Your case intake and supporting documents have been captured and staged for the next legal route.",
            "return_href": "/services",
            "return_label": "Back to Service Ports",
            "next_href": "/modules/signal-dock",
            "next_label": "Continue to Signal Dock",
            "record_id": next_id,
            "file_count": len(saved_files),
            "step_number": 1,
            "step_total": 4,
            "step_name": "Case Dock",
            "why_next": "Case Dock gathers the facts and files. Signal Dock is next because it reviews deadlines, notices, triggers, and risk signals before remedy analysis.",
        },
    )


@app.get("/modules/signal-dock", response_class=HTMLResponse)
def signal_dock(request: Request):
    return render(request, "signal_dock.html")


@app.get("/modules/equity-engine", response_class=HTMLResponse)
def equity_engine(request: Request):
    return render(request, "equity_engine.html")


@app.get("/modules/navigator-ai", response_class=HTMLResponse)
def navigator_ai(request: Request):
    case_context = fetch_latest_case()
    return render(
        request,
        "navigator_ai.html",
        {"case_context": case_context},
    )
