from pathlib import Path
import os
import json
import shutil
import sqlite3
import time
from uuid import uuid4

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routes.financial_engine_test import financial_engine_router
from routes.financial_engine_panel import financial_engine_panel_router
from routes.financial_engine_actions import financial_engine_actions_router
from routes.core_routes import core_routes

app = FastAPI(title="Nautical Compass")
app.include_router(core_routes)
app.include_router(financial_engine_router)
app.include_router(financial_engine_panel_router)
app.include_router(financial_engine_actions_router)

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


def str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def labor_signal_flags() -> dict:
    return {
        "ENABLE_LABOR_SIGNAL_ENGINE": str_to_bool(os.getenv("ENABLE_LABOR_SIGNAL_ENGINE"), True),
        "ENABLE_OPPORTUNITY_SCORING": str_to_bool(os.getenv("ENABLE_OPPORTUNITY_SCORING"), True),
        "ENABLE_SKILL_GAP_ENGINE": str_to_bool(os.getenv("ENABLE_SKILL_GAP_ENGINE"), True),
        "ENABLE_MARKET_ROUTING_ADVISORY": str_to_bool(os.getenv("ENABLE_MARKET_ROUTING_ADVISORY"), True),
        "SHOW_LABOR_WIDGETS_TO_USERS": str_to_bool(os.getenv("SHOW_LABOR_WIDGETS_TO_USERS"), False),
        "SHOW_LABOR_WIDGETS_TO_ADMIN": str_to_bool(os.getenv("SHOW_LABOR_WIDGETS_TO_ADMIN"), True),
        "USE_SIGNAL_ENGINE_IN_MATCHING": str_to_bool(os.getenv("USE_SIGNAL_ENGINE_IN_MATCHING"), False),
    }


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
                generated_docs_json TEXT,
                compliance_json TEXT
            )
            """
        )
        conn.commit()

        columns = [row["name"] for row in conn.execute("PRAGMA table_info(cases)").fetchall()]
        if "compliance_json" not in columns:
            conn.execute("ALTER TABLE cases ADD COLUMN compliance_json TEXT")
            conn.commit()


init_db()


def render(request: Request, template: str, data=None):
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    ctx["labor_signal_flags"] = labor_signal_flags()
    ctx["labor_signal_enabled"] = labor_signal_flags()["ENABLE_LABOR_SIGNAL_ENGINE"]
    return templates.TemplateResponse(template, ctx)


def get_checkout_links():
    entry_access = (
        os.getenv("STRIPE_LINK_ENTRY_ACCESS", "").strip()
        or os.getenv("STRIPE_LINK_LEGAL_BASIC", "").strip()
    )
    further_action = (
        os.getenv("STRIPE_LINK_FURTHER_ACTION", "").strip()
        or os.getenv("STRIPE_LINK_LEGAL_PRO", "").strip()
    )
    labor_signal_basic = os.getenv("STRIPE_LINK_LABOR_SIGNAL_BASIC", "").strip()
    labor_signal_pro = os.getenv("STRIPE_LINK_LABOR_SIGNAL_PRO", "").strip()

    return {
        "entry_access": entry_access,
        "further_action": further_action,
        "labor_signal_basic": labor_signal_basic,
        "labor_signal_pro": labor_signal_pro,
    }


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


def infer_case_route(case_data: dict) -> dict:
    issue = (case_data.get("issue_type") or "").strip().lower()
    title = (case_data.get("matter_title") or "").strip().lower()
    summary = (case_data.get("summary") or "").strip().lower()
    timeline = (case_data.get("timeline") or "").strip().lower()
    parties = (case_data.get("parties") or "").strip().lower()

    combined = " ".join([title, summary, timeline, parties])

    if any(term in issue for term in ["auto finance", "car note", "vehicle finance", "repossession", "auto loan"]):
        return {
            "route_name": "Auto Finance / Repossession Route",
            "rationale": [
                "The issue type identifies a vehicle finance or repossession dispute.",
                "This route depends on contract terms, payment history, notice review, and lender conduct.",
            ],
            "next_actions": [
                "Identify the lender, contract terms, payment history, and any default or repossession notices.",
                "Preserve account statements, repossession notices, texts, emails, and loan paperwork.",
                "Prepare an auto-finance dispute summary and demand outline.",
            ],
            "document_set": [
                "Auto Finance Dispute Summary",
                "Payment / Default Timeline",
                "Repossession Notice Review",
                "Lender Demand Outline",
            ],
        }

    if any(term in issue for term in ["fcra", "credit reporting", "consumer reporting", "credit report"]):
        return {
            "route_name": "FCRA / Consumer Reporting Route",
            "rationale": [
                "The issue type identifies a consumer-reporting or credit-report dispute.",
                "This route depends on dispute chronology, bureau and furnisher conduct, and correction strategy.",
            ],
            "next_actions": [
                "Identify each bureau or furnisher involved.",
                "List dispute dates and responses in order.",
                "Prepare a demand letter and complaint outline.",
            ],
            "document_set": [
                "FCRA Dispute Summary",
                "Consumer Report Error Index",
                "Dispute Timeline",
                "FCRA Demand / Complaint Outline",
            ],
        }

    if any(term in issue for term in ["employment", "workplace discrimination", "retaliation", "wrongful termination", "eeoc"]):
        return {
            "route_name": "Employment / EEOC Route",
            "rationale": [
                "The issue type identifies an employment-related adverse action or workplace dispute.",
                "This route depends on chronology, notices, communications, and agency timing.",
            ],
            "next_actions": [
                "List every adverse action and date in sequence.",
                "Preserve emails, writeups, evaluations, and notices.",
                "Prepare an administrative filing outline.",
            ],
            "document_set": [
                "Employment Matter Summary",
                "Adverse Action Timeline",
                "Workplace Evidence Index",
                "EEOC / Employment Filing Outline",
            ],
        }

    if any(term in issue for term in ["housing", "tenant", "eviction", "lease dispute", "rent"]):
        return {
            "route_name": "Housing / Tenant Defense Route",
            "rationale": [
                "The issue type identifies a housing or tenant-defense matter.",
                "This route depends on notice dates, lease language, and payment and occupancy history.",
            ],
            "next_actions": [
                "Identify hearing dates, notice dates, and payment history.",
                "Preserve all notices and lease language.",
                "Prepare a housing defense outline.",
            ],
            "document_set": [
                "Housing Defense Summary",
                "Notice / Rent Timeline",
                "Lease and Notice Index",
                "Tenant Defense Outline",
            ],
        }

    if any(term in issue for term in ["contract", "breach", "nonpayment", "invoice dispute"]):
        return {
            "route_name": "Contract / Payment Enforcement Route",
            "rationale": [
                "The issue type identifies a contract or payment-enforcement dispute.",
                "This route depends on agreement terms, breach chronology, and payment proof.",
            ],
            "next_actions": [
                "Identify the contract and breach point.",
                "Preserve invoices, communications, and performance proof.",
                "Prepare a breach summary and demand letter.",
            ],
            "document_set": [
                "Contract Dispute Summary",
                "Breach Timeline",
                "Invoice / Payment Evidence Index",
                "Demand for Payment / Breach Outline",
            ],
        }

    if issue == "":
        if any(term in combined for term in ["buick", "car note", "repossession", "vehicle", "auto loan", "lender"]):
            return {
                "route_name": "Auto Finance / Repossession Route",
                "rationale": [
                    "The matter title and facts point to a vehicle finance or repossession dispute.",
                    "This route depends on lender conduct, account history, and notice review.",
                ],
                "next_actions": [
                    "Identify the lender, contract terms, payment history, and any default or repossession notices.",
                    "Preserve account statements, repossession notices, texts, emails, and loan paperwork.",
                    "Prepare an auto-finance dispute summary and demand outline.",
                ],
                "document_set": [
                    "Auto Finance Dispute Summary",
                    "Payment / Default Timeline",
                    "Repossession Notice Review",
                    "Lender Demand Outline",
                ],
            }

    return {
        "route_name": "General Civil / Administrative Review",
        "rationale": [
            "The intake does not yet clearly identify a single legal route.",
            "The matter needs tighter issue labeling before the system should force a narrower lane.",
        ],
        "next_actions": [
            "Clarify the exact issue type in one line.",
            "Refine the timeline and isolate the triggering event.",
            "List all notices, denials, deadlines, and requested relief in order.",
        ],
        "document_set": [
            "Case Intake Summary",
            "Evidence Index",
            "Preliminary Route Outline",
        ],
    }


def validate_actor(request: Request) -> dict:
    actor_type = (request.query_params.get("actor_type") or "public_user").strip()
    actor_role = (request.query_params.get("actor_role") or "case_submitter").strip()
    actor_id = (request.query_params.get("actor_id") or "anonymous").strip()

    permissions = [
        "submit_case",
        "view_route",
        "generate_packet",
    ]

    if actor_role in ["admin", "reviewer", "compliance_officer"]:
        permissions.extend(
            [
                "override_route",
                "review_high_risk_case",
                "view_compliance_gate",
            ]
        )

    return {
        "actor_type": actor_type,
        "actor_role": actor_role,
        "actor_id": actor_id,
        "permissions": permissions,
        "is_verified_actor": actor_id != "anonymous",
    }


def classify_request(case_data: dict, route_data: dict) -> dict:
    route_name = route_data.get("route_name", "General Civil / Administrative Review")
    issue_type = (case_data.get("issue_type") or "").strip().lower()
    requested_outcome = (case_data.get("requested_outcome") or "").strip().lower()

    domain = "legal"
    action_type = "informational_guidance"
    risk_level = "medium"
    requires_human_review = False
    blocking_flags = []

    high_risk_routes = {
        "Auto Finance / Repossession Route",
        "Employment / EEOC Route",
        "Housing / Tenant Defense Route",
    }

    rights_routes = {
        "FCRA / Consumer Reporting Route",
        "Employment / EEOC Route",
    }

    if route_name in rights_routes:
        action_type = "rights_analysis"

    if route_name in high_risk_routes:
        risk_level = "high"
        requires_human_review = True

    if "injunction" in requested_outcome or "emergency" in requested_outcome:
        risk_level = "high"
        requires_human_review = True
        blocking_flags.append("emergency_or_injunctive_relief_requested")

    if issue_type == "":
        blocking_flags.append("issue_type_not_cleanly_stated")

    if route_name == "General Civil / Administrative Review":
        blocking_flags.append("route_confidence_low")
        requires_human_review = True

    return {
        "domain": domain,
        "action_type": action_type,
        "risk_level": risk_level,
        "requires_human_review": requires_human_review,
        "blocking_flags": blocking_flags,
    }


def attach_legal_basis(case_data: dict, route_data: dict) -> list[dict]:
    route_name = route_data.get("route_name", "General Civil / Administrative Review")
    legal_basis = [
        {
            "authority": "Article III Standing",
            "reference": "Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992)",
            "why_it_applies": "Any federal-court facing route should tie injury, causation, and redressability to the matter.",
        },
        {
            "authority": "Real Party in Interest / Capacity",
            "reference": "Rule 17; Rule 9(a)",
            "why_it_applies": "The system should identify who is actually asserting the claim and in what capacity.",
        },
        {
            "authority": "Federal Question Gate",
            "reference": "28 U.S.C. § 1331",
            "why_it_applies": "Any federal-law route should identify whether the matter arises under federal law.",
        },
    ]

    if route_name == "FCRA / Consumer Reporting Route":
        legal_basis.append(
            {
                "authority": "FCRA",
                "reference": "15 U.S.C. § 1681 et seq.",
                "why_it_applies": "Consumer reporting disputes require permissible-purpose, accuracy, reinvestigation, and harm analysis.",
            }
        )

    if route_name == "Employment / EEOC Route":
        legal_basis.append(
            {
                "authority": "Civil Rights / Capacity Analysis",
                "reference": "42 U.S.C. § 1983; Ex parte Young",
                "why_it_applies": "Where public-actor conduct is implicated, the system should distinguish official-capacity and personal-capacity posture.",
            }
        )

    if route_name == "General Civil / Administrative Review":
        legal_basis.append(
            {
                "authority": "Administrative Process Discipline",
                "reference": "5 U.S.C. § 551 et seq.",
                "why_it_applies": "The system should classify whether the matter is best treated as agency action, adjudication, or pre-suit review.",
            }
        )

    return legal_basis


def build_compliance_gate(request: Request, case_data: dict, route_data: dict) -> dict:
    actor = validate_actor(request)
    request_profile = classify_request(case_data, route_data)
    legal_basis = attach_legal_basis(case_data, route_data)

    return {
        "gate_status": "active",
        "actor": actor,
        "request_profile": request_profile,
        "legal_basis": legal_basis,
        "human_review_status": "required" if request_profile["requires_human_review"] else "not_required",
        "audit_stamp": int(time.time()),
    }


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

    summary_title = route_data["document_set"][0] if len(route_data["document_set"]) > 0 else "Case Summary Memorandum"
    timeline_title = route_data["document_set"][1] if len(route_data["document_set"]) > 1 else "Evidence Index"
    review_title = route_data["document_set"][2] if len(route_data["document_set"]) > 2 else "Next-Step Action Brief"
    outline_title = route_data["document_set"][3] if len(route_data["document_set"]) > 3 else "Complaint / Demand Outline"

    summary_text = f"""{summary_title}

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
    summary_file = case_folder / f"{summary_title.lower().replace(' / ', '_').replace(' ', '_')}.txt"
    summary_file.write_text(summary_text, encoding="utf-8")
    generated_docs.append(
        {
            "title": summary_title,
            "url": f"/uploads/{summary_file.relative_to(UPLOAD_ROOT).as_posix()}",
        }
    )

    timeline_text = f"""{timeline_title}

Case ID: {case_data["id"]}
Matter Title: {case_data["matter_title"]}

FILES RECEIVED
"""
    if files:
        for item in files:
            timeline_text += f"- {item['name']}\n"
    else:
        timeline_text += "- No files uploaded.\n"

    timeline_file = case_folder / f"{timeline_title.lower().replace(' / ', '_').replace(' ', '_')}.txt"
    timeline_file.write_text(timeline_text, encoding="utf-8")
    generated_docs.append(
        {
            "title": timeline_title,
            "url": f"/uploads/{timeline_file.relative_to(UPLOAD_ROOT).as_posix()}",
        }
    )

    action_text = f"""{review_title}

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

    review_file = case_folder / f"{review_title.lower().replace(' / ', '_').replace(' ', '_')}.txt"
    review_file.write_text(action_text, encoding="utf-8")
    generated_docs.append(
        {
            "title": review_title,
            "url": f"/uploads/{review_file.relative_to(UPLOAD_ROOT).as_posix()}",
        }
    )

    outline_text = f"""{outline_title}

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
    outline_file = case_folder / f"{outline_title.lower().replace(' / ', '_').replace(' ', '_')}.txt"
    outline_file.write_text(outline_text, encoding="utf-8")
    generated_docs.append(
        {
            "title": outline_title,
            "url": f"/uploads/{outline_file.relative_to(UPLOAD_ROOT).as_posix()}",
        }
    )

    compliance = route_data.get("compliance_gate")
    if compliance:
        gate_text = f"""AI COMPLIANCE GATE REPORT

CASE ID
{case_data["id"]}

GATE STATUS
{compliance.get("gate_status")}

ACTOR
- type: {compliance["actor"].get("actor_type")}
- role: {compliance["actor"].get("actor_role")}
- id: {compliance["actor"].get("actor_id")}
- verified: {compliance["actor"].get("is_verified_actor")}

REQUEST PROFILE
- domain: {compliance["request_profile"].get("domain")}
- action_type: {compliance["request_profile"].get("action_type")}
- risk_level: {compliance["request_profile"].get("risk_level")}
- requires_human_review: {compliance["request_profile"].get("requires_human_review")}

BLOCKING FLAGS
"""
        flags = compliance["request_profile"].get("blocking_flags", [])
        if flags:
            for flag in flags:
                gate_text += f"- {flag}\n"
        else:
            gate_text += "- none\n"

        gate_text += "\nLEGAL BASIS\n"
        for item in compliance.get("legal_basis", []):
            gate_text += f"- {item['authority']}: {item['reference']} | {item['why_it_applies']}\n"

        gate_text += f"\nHUMAN REVIEW STATUS\n{compliance.get('human_review_status')}\n"

        gate_file = case_folder / "ai_compliance_gate_report.txt"
        gate_file.write_text(gate_text, encoding="utf-8")
        generated_docs.append(
            {
                "title": "AI Compliance Gate Report",
                "url": f"/uploads/{gate_file.relative_to(UPLOAD_ROOT).as_posix()}",
            }
        )

    return case_folder_name, generated_docs


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
                generated_docs_json,
                compliance_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(case_data.get("compliance_gate", {})),
            ),
        )
        conn.commit()


def update_case_record(case_data: dict):
    with db_conn() as conn:
        conn.execute(
            """
            UPDATE cases
            SET timeline = ?,
                summary = ?,
                requested_outcome = ?,
                case_folder_name = ?,
                route_name = ?,
                route_json = ?,
                files_json = ?,
                generated_docs_json = ?,
                compliance_json = ?
            WHERE id = ?
            """,
            (
                case_data["timeline"],
                case_data["summary"],
                case_data["requested_outcome"],
                case_data["case_folder_name"],
                case_data["route"]["route_name"],
                json.dumps(case_data["route"]),
                json.dumps(case_data["files"]),
                json.dumps(case_data["generated_docs"]),
                json.dumps(case_data.get("compliance_gate", {})),
                case_data["id"],
            ),
        )
        conn.commit()


def merge_route_module_state(existing_module_state: dict, updates: dict) -> dict:
    merged = {
        "case_dock": existing_module_state.get("case_dock", {}),
        "signal_dock": existing_module_state.get("signal_dock", {}),
        "equity_engine": existing_module_state.get("equity_engine", {}),
    }
    merged.update(updates)
    return merged


def fetch_latest_case():
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM cases ORDER BY id DESC LIMIT 1").fetchone()

    if not row:
        return None

    compliance = {}
    if "compliance_json" in row.keys() and row["compliance_json"]:
        compliance = json.loads(row["compliance_json"])

    route = json.loads(row["route_json"]) if row["route_json"] else {}
    if compliance and "compliance_gate" not in route:
        route["compliance_gate"] = compliance

    route.setdefault("module_state", {})
    route["module_state"].setdefault(
        "case_dock",
        {
            "status": "complete",
            "completed_at": row["created_at"],
            "snapshot": {
                "matter_title": row["matter_title"],
                "jurisdiction": row["jurisdiction"],
                "issue_type": row["issue_type"],
                "requested_outcome": row["requested_outcome"],
                "parties": row["parties"],
                "timeline": row["timeline"],
                "summary": row["summary"],
                "file_count": len(json.loads(row["files_json"])) if row["files_json"] else 0,
            },
        },
    )
    route["module_state"].setdefault(
        "signal_dock", {"status": "pending", "completed_at": None, "review": {}}
    )
    route["module_state"].setdefault(
        "equity_engine", {"status": "pending", "completed_at": None, "review": {}}
    )

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
        "route": route,
        "files": json.loads(row["files_json"]) if row["files_json"] else [],
        "generated_docs": json.loads(row["generated_docs_json"]) if row["generated_docs_json"] else [],
        "further_action_required": True,
        "compliance_gate": compliance or route.get("compliance_gate", {}),
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "index.html")


@app.get("/health")
def health():
    module_imported = False
    module_error = None

    try:
        from modules.labor_signal.router import router as labor_signal_router  # noqa: F401
        module_imported = True
    except Exception as exc:
        module_error = str(exc)

    return JSONResponse(
        {
            "ok": True,
            "app": "Nautical Compass",
            "labor_signal_module_imported": module_imported,
            "labor_signal_module_error": module_error,
            "labor_signal_flags": labor_signal_flags(),
        }
    )


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
    message: str = Form(""),
):
    return RedirectResponse("/lead/thanks", status_code=303)


@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return render(request, "lead_thanks.html")


@app.get("/sponsor", response_class=HTMLResponse)
def sponsor(request: Request):
    return render(request, "sponsor.html")


@app.get("/checkout", response_class=HTMLResponse)
def checkout(request: Request):
    return render(request, "checkout.html", {"checkout_links": get_checkout_links()})


@app.get("/checkout/{plan_key}", response_class=HTMLResponse)
def checkout_plan(request: Request, plan_key: str):
    links = get_checkout_links()
    checkout_url = links.get(plan_key, "")

    plan_titles = {
        "entry_access": "Entry Access — $25",
        "further_action": "Further Action Required — $135",
        "labor_signal_basic": "Labor Signal Basic",
        "labor_signal_pro": "Labor Signal Pro",
    }

    if checkout_url:
        return RedirectResponse(checkout_url, status_code=302)

    return render(
        request,
        "subscription_setup_needed.html",
        {
            "plan_key": plan_key,
            "plan_title": plan_titles.get(plan_key, "Selected Plan"),
        },
    )


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
    return render(request, "intake_form.html")


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
        next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM cases").fetchone()[0]

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
    route_data["module_state"] = {
        "case_dock": {
            "status": "complete",
            "completed_at": int(time.time()),
            "snapshot": {
                "matter_title": matter_title,
                "jurisdiction": jurisdiction,
                "issue_type": issue_type,
                "requested_outcome": requested_outcome,
                "parties": parties,
                "timeline": timeline,
                "summary": summary,
                "file_count": len(saved_files),
            },
        },
        "signal_dock": {
            "status": "pending",
            "completed_at": None,
            "review": {},
        },
        "equity_engine": {
            "status": "pending",
            "completed_at": None,
            "review": {},
        },
    }
    compliance_gate = build_compliance_gate(request, case_data, route_data)
    route_data["compliance_gate"] = compliance_gate

    case_folder_name, generated_docs = write_case_folder(case_data, saved_files, route_data)

    case_data["route"] = route_data
    case_data["case_folder_name"] = case_folder_name
    case_data["generated_docs"] = generated_docs
    case_data["compliance_gate"] = compliance_gate

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
            "why_next": "Case Dock gathers the facts and files. Signal Dock is next because it reviews deadlines, notices, triggers, risk signals, and the AI Compliance Gate before remedy analysis.",
        },
    )


@app.get("/modules/case-update", response_class=HTMLResponse)
def case_update(request: Request):
    case_context = fetch_latest_case()
    return render(request, "case_update.html", {"case_context": case_context})


@app.post("/modules/case-update")
async def case_update_submit(
    request: Request,
    additional_facts: str = Form(""),
    additional_timeline: str = Form(""),
    updated_requested_outcome: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    case_context = fetch_latest_case()
    if not case_context:
        return RedirectResponse("/modules/case-dock", status_code=303)

    saved_files = save_uploads(files, CASE_DOCK_UPLOADS)

    updated_summary = case_context.get("summary", "")
    if additional_facts.strip():
        updated_summary = f"{updated_summary}\n\nSUPPLEMENTAL FACTS\n{additional_facts}".strip()

    updated_timeline = case_context.get("timeline", "")
    if additional_timeline.strip():
        updated_timeline = f"{updated_timeline}\n\nSUPPLEMENTAL TIMELINE NOTES\n{additional_timeline}".strip()

    requested_outcome = case_context.get("requested_outcome", "")
    if updated_requested_outcome.strip():
        requested_outcome = updated_requested_outcome.strip()

    merged_files = list(case_context.get("files", [])) + saved_files

    case_data = {
        "id": case_context["id"],
        "matter_title": case_context["matter_title"],
        "jurisdiction": case_context["jurisdiction"],
        "issue_type": case_context["issue_type"],
        "parties": case_context["parties"],
        "timeline": updated_timeline,
        "summary": updated_summary,
        "requested_outcome": requested_outcome,
        "files": merged_files,
        "created_at": case_context["created_at"],
    }

    route_data = infer_case_route(case_data)
    existing_module_state = case_context.get("route", {}).get("module_state", {})
    route_data["module_state"] = merge_route_module_state(
        existing_module_state,
        {
            "case_dock": {
                "status": "complete",
                "completed_at": existing_module_state.get("case_dock", {}).get("completed_at") or case_context.get("created_at"),
                "snapshot": {
                    "matter_title": case_data["matter_title"],
                    "jurisdiction": case_data["jurisdiction"],
                    "issue_type": case_data["issue_type"],
                    "requested_outcome": case_data["requested_outcome"],
                    "parties": case_data["parties"],
                    "timeline": case_data["timeline"],
                    "summary": case_data["summary"],
                    "file_count": len(merged_files),
                },
            }
        },
    )
    compliance_gate = build_compliance_gate(request, case_data, route_data)
    route_data["compliance_gate"] = compliance_gate

    case_folder_name, generated_docs = write_case_folder(case_data, merged_files, route_data)

    case_data["route"] = route_data
    case_data["case_folder_name"] = case_folder_name
    case_data["generated_docs"] = generated_docs
    case_data["compliance_gate"] = compliance_gate

    update_case_record(case_data)

    return render(
        request,
        "submission_success.html",
        {
            "title": "Case Update Saved",
            "summary": "Your additional facts and supporting files were added to the existing matter.",
            "return_href": "/modules/navigator-ai",
            "return_label": "Back to Navigator AI",
            "next_href": "/modules/draft-packet",
            "next_label": "Open Updated Draft Packet",
            "record_id": case_data["id"],
            "file_count": len(saved_files),
            "step_number": 4,
            "step_total": 4,
            "step_name": "Case Continuation Update",
            "why_next": "The original intake remains active. This update has been attached to the existing matter and the packet has been refreshed.",
        },
    )


@app.get("/modules/signal-dock", response_class=HTMLResponse)
def signal_dock(request: Request):
    case_context = fetch_latest_case()
    return render(request, "signal_dock.html", {"case_context": case_context})


@app.post("/modules/signal-dock")
async def signal_dock_submit(
    request: Request,
    critical_deadlines: str = Form(""),
    notice_signals: str = Form(""),
    risk_flags: str = Form(""),
    signal_summary: str = Form(""),
):
    case_context = fetch_latest_case()
    if not case_context:
        return RedirectResponse("/modules/case-dock", status_code=303)

    signal_block_parts = []
    if critical_deadlines.strip():
        signal_block_parts.append(f"CRITICAL DEADLINES\n{critical_deadlines.strip()}")
    if notice_signals.strip():
        signal_block_parts.append(f"NOTICE SIGNALS\n{notice_signals.strip()}")
    if risk_flags.strip():
        signal_block_parts.append(f"RISK FLAGS\n{risk_flags.strip()}")
    if signal_summary.strip():
        signal_block_parts.append(f"SIGNAL SUMMARY\n{signal_summary.strip()}")

    signal_block = "\n\n".join(signal_block_parts)

    updated_summary = case_context.get("summary", "")
    if signal_block:
        updated_summary = f"{updated_summary}\n\nSIGNAL DOCK REVIEW\n{signal_block}".strip()

    signal_review = {
        "critical_deadlines": critical_deadlines.strip(),
        "notice_signals": notice_signals.strip(),
        "risk_flags": risk_flags.strip(),
        "signal_summary": signal_summary.strip(),
    }

    case_data = {
        "id": case_context["id"],
        "matter_title": case_context["matter_title"],
        "jurisdiction": case_context["jurisdiction"],
        "issue_type": case_context["issue_type"],
        "parties": case_context["parties"],
        "timeline": case_context["timeline"],
        "summary": updated_summary,
        "requested_outcome": case_context["requested_outcome"],
        "files": case_context.get("files", []),
        "created_at": case_context["created_at"],
    }

    route_data = infer_case_route(case_data)
    existing_module_state = case_context.get("route", {}).get("module_state", {})
    route_data["module_state"] = merge_route_module_state(
        existing_module_state,
        {
            "case_dock": existing_module_state.get("case_dock", {
                "status": "complete",
                "completed_at": case_context.get("created_at"),
                "snapshot": {
                    "matter_title": case_context["matter_title"],
                    "jurisdiction": case_context["jurisdiction"],
                    "issue_type": case_context["issue_type"],
                    "requested_outcome": case_context["requested_outcome"],
                    "parties": case_context["parties"],
                    "timeline": case_context["timeline"],
                    "summary": case_context.get("summary", ""),
                    "file_count": len(case_context.get("files", [])),
                },
            }),
            "signal_dock": {
                "status": "complete",
                "completed_at": int(time.time()),
                "review": signal_review,
            },
        },
    )
    compliance_gate = build_compliance_gate(request, case_data, route_data)
    route_data["compliance_gate"] = compliance_gate

    case_folder_name, generated_docs = write_case_folder(
        case_data, case_data["files"], route_data
    )

    case_data["route"] = route_data
    case_data["case_folder_name"] = case_folder_name
    case_data["generated_docs"] = generated_docs
    case_data["compliance_gate"] = compliance_gate

    update_case_record(case_data)

    return render(
        request,
        "submission_success.html",
        {
            "title": "Signal Review Saved",
            "summary": "Deadlines, notice signals, and risk flags have been captured and appended to the active matter.",
            "return_href": "/modules/case-dock",
            "return_label": "Back to Case Dock",
            "next_href": "/modules/equity-engine",
            "next_label": "Continue to Equity Engine",
            "record_id": case_context["id"],
            "file_count": 0,
            "step_number": 2,
            "step_total": 4,
            "step_name": "Signal Dock",
            "why_next": "Signal review is complete. Equity Engine is the next step where requested relief, equitable posture, and strategic pressure path are framed before the draft packet is built.",
        },
    )


@app.get("/modules/equity-engine", response_class=HTMLResponse)
def equity_engine(request: Request):
    case_context = fetch_latest_case()
    return render(request, "equity_engine.html", {"case_context": case_context})


@app.post("/modules/equity-engine")
async def equity_engine_submit(
    request: Request,
    relief_sought: str = Form(""),
    equitable_posture: str = Form(""),
    pressure_path: str = Form(""),
    urgency_level: str = Form(""),
    equity_notes: str = Form(""),
):
    case_context = fetch_latest_case()
    if not case_context:
        return RedirectResponse("/modules/case-dock", status_code=303)

    equity_block_parts = []
    if relief_sought.strip():
        equity_block_parts.append(f"RELIEF SOUGHT\n{relief_sought.strip()}")
    if equitable_posture.strip():
        equity_block_parts.append(f"EQUITABLE POSTURE\n{equitable_posture.strip()}")
    if pressure_path.strip():
        equity_block_parts.append(f"PRESSURE PATH\n{pressure_path.strip()}")
    if urgency_level.strip():
        equity_block_parts.append(f"URGENCY LEVEL\n{urgency_level.strip()}")
    if equity_notes.strip():
        equity_block_parts.append(f"EQUITY NOTES\n{equity_notes.strip()}")

    equity_block = "\n\n".join(equity_block_parts)

    updated_summary = case_context.get("summary", "")
    if equity_block:
        updated_summary = f"{updated_summary}\n\nEQUITY ENGINE REVIEW\n{equity_block}".strip()

    updated_outcome = case_context.get("requested_outcome", "")
    if relief_sought.strip():
        updated_outcome = relief_sought.strip()

    equity_review = {
        "relief_sought": relief_sought.strip(),
        "equitable_posture": equitable_posture.strip(),
        "pressure_path": pressure_path.strip(),
        "urgency_level": urgency_level.strip(),
        "equity_notes": equity_notes.strip(),
    }

    case_data = {
        "id": case_context["id"],
        "matter_title": case_context["matter_title"],
        "jurisdiction": case_context["jurisdiction"],
        "issue_type": case_context["issue_type"],
        "parties": case_context["parties"],
        "timeline": case_context["timeline"],
        "summary": updated_summary,
        "requested_outcome": updated_outcome,
        "files": case_context.get("files", []),
        "created_at": case_context["created_at"],
    }

    route_data = infer_case_route(case_data)
    existing_module_state = case_context.get("route", {}).get("module_state", {})
    route_data["module_state"] = merge_route_module_state(
        existing_module_state,
        {
            "case_dock": existing_module_state.get("case_dock", {
                "status": "complete",
                "completed_at": case_context.get("created_at"),
                "snapshot": {
                    "matter_title": case_context["matter_title"],
                    "jurisdiction": case_context["jurisdiction"],
                    "issue_type": case_context["issue_type"],
                    "requested_outcome": case_context["requested_outcome"],
                    "parties": case_context["parties"],
                    "timeline": case_context["timeline"],
                    "summary": case_context.get("summary", ""),
                    "file_count": len(case_context.get("files", [])),
                },
            }),
            "equity_engine": {
                "status": "complete",
                "completed_at": int(time.time()),
                "review": equity_review,
            },
        },
    )
    compliance_gate = build_compliance_gate(request, case_data, route_data)
    route_data["compliance_gate"] = compliance_gate

    case_folder_name, generated_docs = write_case_folder(
        case_data, case_data["files"], route_data
    )

    case_data["route"] = route_data
    case_data["case_folder_name"] = case_folder_name
    case_data["generated_docs"] = generated_docs
    case_data["compliance_gate"] = compliance_gate

    update_case_record(case_data)

    return render(
        request,
        "submission_success.html",
        {
            "title": "Equity Review Saved",
            "summary": "Relief framing, equitable posture, and pressure path have been captured and added to the active matter.",
            "return_href": "/modules/signal-dock",
            "return_label": "Back to Signal Dock",
            "next_href": "/modules/navigator-ai",
            "next_label": "Continue to Navigator AI",
            "record_id": case_context["id"],
            "file_count": 0,
            "step_number": 3,
            "step_total": 4,
            "step_name": "Equity Engine",
            "why_next": "Equity review is complete. Navigator AI is the next step where the full case context, route, and remedy framing are assembled into a recommended action path and draft packet.",
        },
    )


@app.get("/modules/labor-signal", response_class=HTMLResponse)
def labor_signal_page(request: Request):
    return render(request, "labor_signal.html")


@app.get("/modules/navigator-ai", response_class=HTMLResponse)
def navigator_ai(request: Request):
    case_context = fetch_latest_case()
    return render(request, "navigator_ai.html", {"case_context": case_context})


@app.get("/modules/draft-packet", response_class=HTMLResponse)
def draft_packet(request: Request):
    case_context = fetch_latest_case()
    return render(request, "draft_packet.html", {"case_context": case_context})


try:
    if labor_signal_flags()["ENABLE_LABOR_SIGNAL_ENGINE"]:
        from modules.labor_signal.router import router as labor_signal_router
        app.include_router(labor_signal_router)
except Exception as exc:
    print(f"[labor_signal] router not loaded: {exc}")
