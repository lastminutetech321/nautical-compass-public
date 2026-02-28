import os
import sqlite3
import smtplib
import hashlib
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Dict, Any, List

import stripe
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


# =========================
# PATHS (LOCKED)
# =========================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nc.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


# =========================
# APP
# =========================
app = FastAPI(title="Nautical Compass Intake", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =========================
# CLEAN / ENV HELPERS
# =========================
def _clean(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", "").strip()

def _clean_url(s: str) -> str:
    s = _clean(s)
    if s.lower().startswith("value:"):
        s = s.split(":", 1)[1].strip()
    return s

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# =========================
# STRIPE CONFIG
# =========================
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

SUCCESS_URL = _clean_url(os.getenv("SUCCESS_URL", ""))
CANCEL_URL = _clean_url(os.getenv("CANCEL_URL", ""))

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


# =========================
# EMAIL (OPTIONAL)
# =========================
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))


# =========================
# ADMIN + DEV TOKEN
# =========================
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))


def require_admin(k: Optional[str], key: Optional[str]):
    supplied = _clean(k or "") or _clean(key or "")
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured in environment variables.")
    if not supplied or supplied != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized (bad admin key).")


# =========================
# DB
# =========================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    # NC subscriber intake
    cur.execute("""
        CREATE TABLE IF NOT EXISTS intake (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_email TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            service_requested TEXT NOT NULL,
            notes TEXT,
            facts_json TEXT,
            flags_json TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Public lead intake
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            company TEXT,
            interest TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Partner/manufacturer intake
    cur.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            role TEXT,
            product_type TEXT,
            website TEXT,
            regions TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Subscribers
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Magic links
    cur.execute("""
        CREATE TABLE IF NOT EXISTS magic_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # AVPT client intake (Production Company)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS avpt_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            contact_phone TEXT,

            event_name TEXT,
            event_type TEXT,
            venue_name TEXT,
            venue_address TEXT,
            city TEXT,
            state TEXT,

            load_in_date TEXT,
            show_date TEXT,
            load_out_date TEXT,

            crew_counts TEXT,
            gear_scope TEXT,
            schedule_notes TEXT,

            budget_range TEXT,
            rate_expectation TEXT,
            payment_terms TEXT,

            point_of_contact_on_site TEXT,
            safety_notes TEXT,

            requires_coi TEXT,
            po_required TEXT,

            routing_json TEXT,
            flags_json TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # LMT worker intake (Labor/Tech)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lmt_workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            legal_name TEXT NOT NULL,
            preferred_name TEXT,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            home_city TEXT,
            home_state TEXT,

            worker_type TEXT,
            primary_role TEXT,
            secondary_roles TEXT,
            certifications TEXT,

            availability_window TEXT,
            availability_notes TEXT,

            transportation_mode TEXT,
            truck_size TEXT,
            liftgate TEXT,

            travel_ok TEXT,
            per_diem_required TEXT,

            rate_target TEXT,
            min_rate TEXT,

            tax_ready TEXT,
            business_name TEXT,
            tax_classification TEXT,
            ein_last4 TEXT,
            insurance_ready TEXT,

            notes TEXT,

            routing_json TEXT,
            flags_json TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# EMAIL SENDER
# =========================
def send_email(to_email: str, subject: str, body: str):
    if not (EMAIL_USER and EMAIL_PASS):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg.set_content(body)

        # Default Gmail. If you switch to Mailgun SMTP later, update host/port.
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)


# =========================
# MAGIC LINKS
# =========================
def issue_magic_link(email: str, hours: int = 24) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = sha256(token)
    expires = (datetime.utcnow() + timedelta(hours=hours)).isoformat()

    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO magic_links (email, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (email.lower(), token_hash, expires, now_iso())
    )
    conn.commit()
    conn.close()
    return token


def validate_magic_link(token: str) -> Optional[str]:
    token_hash = sha256(token)
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT email, expires_at FROM magic_links WHERE token_hash = ? ORDER BY id DESC LIMIT 1",
        (token_hash,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires_at:
        return None

    return row["email"]


def is_active_subscriber(email: str) -> bool:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM subscribers WHERE email = ? LIMIT 1", (email.lower(),))
    row = cur.fetchone()
    conn.close()
    return bool(row) and row["status"] == "active"


def upsert_subscriber_active(email: str, customer_id: str = "", subscription_id: str = ""):
    email = (email or "").lower().strip()
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO subscribers (email, stripe_customer_id, stripe_subscription_id, status, created_at, updated_at)
        VALUES (?, ?, ?, 'active', ?, ?)
        ON CONFLICT(email) DO UPDATE SET
          stripe_customer_id=excluded.stripe_customer_id,
          stripe_subscription_id=excluded.stripe_subscription_id,
          status='active',
          updated_at=excluded.updated_at
    """, (email, customer_id, subscription_id, now_iso(), now_iso()))
    conn.commit()
    conn.close()


def require_subscriber_token(token: Optional[str]):
    if not token:
        return None, HTMLResponse("Missing token.", status_code=401)

    email = validate_magic_link(token)
    if not email:
        return None, HTMLResponse("Invalid or expired link.", status_code=401)

    if not is_active_subscriber(email):
        return None, HTMLResponse("Subscription not active.", status_code=403)

    return email, None


# =========================
# LEGAL SPINE v1 (CURATED)
# Dual-mode: Basic + Court-Ready
# =========================
LEGAL_SPINE: Dict[str, Dict[str, Any]] = {
    "standing_article_iii": {
        "title": "Article III Standing (Federal Court)",
        "basic": [
            "To be heard in federal court, you generally must show: (1) real harm, (2) it was caused by the defendant, and (3) the court can fix it.",
        ],
        "court_ready": [
            {
                "rule": "Plaintiff must establish (1) injury in fact, (2) causation, and (3) redressability.",
                "cite": "Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992)."
            },
            {
                "rule": "A statutory violation alone may be insufficient without concrete harm.",
                "cite": "Spokeo, Inc. v. Robins, 578 U.S. 330 (2016); TransUnion LLC v. Ramirez, 594 U.S. 413 (2021)."
            },
        ],
        "facts_needed": [
            "What exactly happened (dates, actors, location)",
            "What harm occurred (financial loss, denial of service, reputational harm, loss of opportunity, etc.)",
            "How defendant’s act caused it (the link)",
            "What remedy you want (money, injunction, correction, access, stop conduct)",
        ],
    },
    "capacity_official_individual": {
        "title": "Individual vs Official Capacity (Suing Officials)",
        "basic": [
            "If you sue an official personally, you seek damages from them. If you sue officially, you usually seek policy change or injunctions.",
        ],
        "court_ready": [
            {
                "rule": "Official-capacity suits are treated as suits against the governmental entity; individual-capacity targets the person.",
                "cite": "Kentucky v. Graham, 473 U.S. 159 (1985)."
            },
            {
                "rule": "State officials can be sued for prospective injunctive relief to stop ongoing violations (Ex parte Young).",
                "cite": "Ex parte Young, 209 U.S. 123 (1908)."
            },
            {
                "rule": "State officials can be liable in personal capacity for constitutional violations under § 1983.",
                "cite": "Hafer v. Melo, 502 U.S. 21 (1991)."
            },
        ],
        "facts_needed": [
            "Who did what (specific official actions)",
            "Whether harm is ongoing (for injunction)",
            "Whether you want damages vs prospective relief",
        ],
    },
}


def spine_pick(service_requested: str) -> List[str]:
    s = (service_requested or "").lower()
    topics = ["standing_article_iii"]
    if any(x in s for x in ["official", "1983", "civil rights", "injunction", "government"]):
        topics.append("capacity_official_individual")
    return topics


# =========================
# RISK FLAGS v1 (NC)
# =========================
def risk_flags_v1_nc(intake: Dict[str, Any]) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []

    service = (intake.get("service_requested") or "").lower().strip()
    notes = (intake.get("notes") or "").strip()

    if len(notes) < 40:
        flags.append({
            "code": "RF_FACTS_THIN",
            "title": "Thin facts",
            "severity": "medium",
            "why": "Not enough factual detail to triage quickly or map standing/capacity.",
            "fix": "Add timeline: what happened, when, who, where, harm, what you want."
        })

    wants = intake.get("wants") or ""
    if not wants:
        flags.append({
            "code": "RF_REMEDY_UNCLEAR",
            "title": "Requested relief unclear",
            "severity": "medium",
            "why": "Redressability depends on what the court/decision-maker can order.",
            "fix": "Specify: damages amount, correction, injunction/stop conduct, record release, etc."
        })

    injury = intake.get("injury") or ""
    if not injury:
        flags.append({
            "code": "RF_INJURY_UNSTATED",
            "title": "Injury not stated",
            "severity": "high",
            "why": "Standing typically fails without a concrete injury (harm).",
            "fix": "State your harm: money, denial, lost work, time, privacy invasion, reputational harm, etc."
        })

    if "contract" in service and ("contract" not in notes.lower()):
        flags.append({
            "code": "RF_DOC_MISSING_CONTRACT",
            "title": "Contract not referenced",
            "severity": "low",
            "why": "Contract review requires the document or key clauses.",
            "fix": "Attach or paste relevant clauses, parties, dates, payment terms, termination, liability."
        })

    if "arbitration" in service and ("arbitration" not in notes.lower()):
        flags.append({
            "code": "RF_ARB_FORUM_UNKNOWN",
            "title": "Arbitration clause/forum unknown",
            "severity": "medium",
            "why": "Package depends on clause, provider (AAA/JAMS), deadlines, and notice requirements.",
            "fix": "Provide clause text or where it appears; note any deadlines or prior notices."
        })

    if "evidence" in service and ("photo" not in notes.lower() and "email" not in notes.lower() and "text" not in notes.lower()):
        flags.append({
            "code": "RF_EVIDENCE_UNLISTED",
            "title": "Evidence not listed",
            "severity": "low",
            "why": "We can’t map exhibits to claims without knowing what exists.",
            "fix": "List what you have: screenshots, emails, invoices, contracts, recordings, witnesses."
        })

    return flags


# =========================
# RISK FLAGS v1 (AVPT CLIENT)
# =========================
def risk_flags_v1_avpt(intake: Dict[str, Any]) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []

    company = (intake.get("company_name") or "").strip()
    email = (intake.get("contact_email") or "").strip()
    event_type = (intake.get("event_type") or "").strip()
    venue_address = (intake.get("venue_address") or "").strip()
    show_date = (intake.get("show_date") or "").strip()
    crew_counts = (intake.get("crew_counts") or "").strip()
    budget_range = (intake.get("budget_range") or "").strip()
    requires_coi = (intake.get("requires_coi") or "").strip()
    po_required = (intake.get("po_required") or "").strip()

    if not company or len(company) < 2:
        flags.append({
            "code": "AVPT_COMPANY_MISSING",
            "title": "Company name missing",
            "severity": "high",
            "why": "We can’t route staffing or invoicing without the production entity name.",
            "fix": "Enter your production company name (legal or DBA)."
        })

    if "@" not in email:
        flags.append({
            "code": "AVPT_EMAIL_INVALID",
            "title": "Contact email invalid",
            "severity": "high",
            "why": "Scheduling + confirmations require a reachable email.",
            "fix": "Enter a valid contact email."
        })

    if not event_type:
        flags.append({
            "code": "AVPT_EVENT_TYPE_MISSING",
            "title": "Event type missing",
            "severity": "medium",
            "why": "Crew build depends on whether this is corporate, concert, gala, livestream, etc.",
            "fix": "Select or describe the event type."
        })

    if not show_date:
        flags.append({
            "code": "AVPT_DATE_MISSING",
            "title": "Show date missing",
            "severity": "high",
            "why": "We can’t forecast labor availability or hold crew without dates.",
            "fix": "Provide at least the show date; load-in/load-out are strongly recommended."
        })

    if not venue_address or len(venue_address) < 8:
        flags.append({
            "code": "AVPT_VENUE_ADDRESS_MISSING",
            "title": "Venue address missing",
            "severity": "high",
            "why": "Routing, call times, parking, and logistics fail without the real address.",
            "fix": "Enter the full venue address (street + city + state)."
        })

    if not crew_counts:
        flags.append({
            "code": "AVPT_CREW_COUNTS_EMPTY",
            "title": "Crew request not specified",
            "severity": "medium",
            "why": "We can’t price or allocate without counts per role (e.g., 2 loaders, 1 A2, 1 V1).",
            "fix": "Provide counts by role or rough headcount."
        })

    if not budget_range:
        flags.append({
            "code": "AVPT_BUDGET_UNKNOWN",
            "title": "Budget range not provided",
            "severity": "medium",
            "why": "Budget anchors rate transparency and prevents mismatched expectations.",
            "fix": "Provide budget range or max rate per role."
        })

    # COI / PO flags (not “bad”, but operational blockers)
    if requires_coi.lower() in ("yes", "y", "required") and po_required.lower() in ("yes", "y", "required"):
        flags.append({
            "code": "AVPT_ADMIN_BLOCKERS",
            "title": "COI + PO required",
            "severity": "low",
            "why": "These are normal, but they add lead time. We must collect paperwork early.",
            "fix": "Have COI holder + PO process ready before crew confirmation."
        })

    return flags


def route_v1_avpt(intake: Dict[str, Any], flags: List[Dict[str, str]]) -> Dict[str, Any]:
    # Simple, deterministic routing core (upgrade later)
    crew_counts = (intake.get("crew_counts") or "").lower()
    event_type = (intake.get("event_type") or "").lower()
    gear_scope = (intake.get("gear_scope") or "").lower()

    lane = "avpt_client"
    priority = "standard"

    if any(f["severity"] == "high" for f in flags):
        priority = "blocked_missing_critical"

    if "concert" in event_type or "festival" in event_type:
        priority = "high_volume"
    if "led" in gear_scope or "wall" in gear_scope:
        priority = "video_heavy"
    if "a1" in crew_counts or "a2" in crew_counts or "foh" in crew_counts:
        priority = "audio_heavy"

    next_steps = []
    if priority == "blocked_missing_critical":
        next_steps.append("Fix High severity flags, then resubmit or reply with missing details.")
    else:
        next_steps.extend([
            "Confirm venue address + dates.",
            "Confirm crew counts per role + call times.",
            "Confirm budget/rate expectations + payment terms.",
            "Issue staffing plan + confirmations.",
        ])

    return {
        "lane": lane,
        "priority": priority,
        "next_steps": next_steps,
    }


# =========================
# RISK FLAGS v1 (LMT WORKER)
# =========================
def risk_flags_v1_lmt(intake: Dict[str, Any]) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []

    legal_name = (intake.get("legal_name") or "").strip()
    email = (intake.get("email") or "").strip()
    phone = (intake.get("phone") or "").strip()
    worker_type = (intake.get("worker_type") or "").strip()
    primary_role = (intake.get("primary_role") or "").strip()

    tax_ready = (intake.get("tax_ready") or "").strip().lower()
    tax_classification = (intake.get("tax_classification") or "").strip()

    transportation = (intake.get("transportation_mode") or "").strip().lower()
    truck_size = (intake.get("truck_size") or "").strip()
    liftgate = (intake.get("liftgate") or "").strip().lower()

    if not legal_name or len(legal_name) < 4:
        flags.append({
            "code": "LMT_LEGAL_NAME_MISSING",
            "title": "Legal name missing",
            "severity": "high",
            "why": "Payroll/tax paperwork and credentialing cannot be generated without legal name.",
            "fix": "Enter your legal name as it appears on ID."
        })

    if "@" not in email:
        flags.append({
            "code": "LMT_EMAIL_INVALID",
            "title": "Email invalid",
            "severity": "high",
            "why": "Booking + confirmations rely on email.",
            "fix": "Enter a valid email."
        })

    if len(phone) < 7:
        flags.append({
            "code": "LMT_PHONE_MISSING",
            "title": "Phone missing/too short",
            "severity": "high",
            "why": "Field dispatch requires a reachable phone.",
            "fix": "Enter a valid phone number."
        })

    if not worker_type:
        flags.append({
            "code": "LMT_WORKER_TYPE_EMPTY",
            "title": "Worker type not selected",
            "severity": "medium",
            "why": "Routing differs for 1099 vs W2 vs vendor company.",
            "fix": "Choose: 1099 contractor / W2 employee / Vendor company."
        })

    if not primary_role:
        flags.append({
            "code": "LMT_ROLE_EMPTY",
            "title": "Primary role not selected",
            "severity": "medium",
            "why": "Matching requires at least one primary role.",
            "fix": "Select your primary role (e.g., Stagehand, A2, V1, LED Tech, Rigger)."
        })

    # Tax readiness flags (do NOT collect SSN here)
    if tax_ready in ("no", "not_ready", "later", ""):
        flags.append({
            "code": "LMT_TAX_NOT_READY",
            "title": "Tax setup not ready",
            "severity": "medium",
            "why": "Some clients will not book without W-9/COI details ready.",
            "fix": "Mark tax-ready = Yes once business name + tax classification are set."
        })

    if tax_ready in ("yes", "y", "true") and not tax_classification:
        flags.append({
            "code": "LMT_TAX_CLASS_MISSING",
            "title": "Tax classification missing",
            "severity": "low",
            "why": "Classification is required to pre-fill a W-9 style profile.",
            "fix": "Choose: Individual/Sole Prop, LLC, S-Corp, C-Corp."
        })

    # Transportation/vehicle clarity (not always required, but important for logistics roles)
    if "truck" in transportation or "van" in transportation:
        if not truck_size:
            flags.append({
                "code": "LMT_TRUCK_SIZE_MISSING",
                "title": "Truck/van size not specified",
                "severity": "low",
                "why": "Some calls require box truck vs sprinter vs pickup.",
                "fix": "Select your truck size."
            })
        if liftgate not in ("yes", "no", "") and liftgate:
            flags.append({
                "code": "LMT_LIFTGATE_UNKNOWN",
                "title": "Liftgate value unclear",
                "severity": "low",
                "why": "Liftgate impacts load-in planning.",
                "fix": "Choose Yes or No for liftgate."
            })

    return flags


def route_v1_lmt(intake: Dict[str, Any], flags: List[Dict[str, str]]) -> Dict[str, Any]:
    primary_role = (intake.get("primary_role") or "").lower()
    certifications = (intake.get("certifications") or "").lower()
    availability = (intake.get("availability_window") or "").lower()

    lane = "lmt_worker"
    bucket = "general_pool"

    if any(f["severity"] == "high" for f in flags):
        bucket = "blocked_missing_critical"

    # quick role buckets
    if any(x in primary_role for x in ["rigger", "rigging"]):
        bucket = "rigging"
    elif any(x in primary_role for x in ["a1", "a2", "audio"]):
        bucket = "audio"
    elif any(x in primary_role for x in ["v1", "v2", "video", "led"]):
        bucket = "video_led"
    elif any(x in primary_role for x in ["stagehand", "loader", "pusher"]):
        bucket = "general_crew"

    # certifications influence
    if "forklift" in certifications or "osha" in certifications:
        bucket = f"{bucket}_certified"

    # availability influence (simple)
    priority = "standard"
    if "10+" in availability or "full" in availability:
        priority = "high_availability"

    next_steps = []
    if bucket == "blocked_missing_critical":
        next_steps.append("Fix High severity flags, then resubmit.")
    else:
        next_steps.extend([
            "Confirm roles + availability window.",
            "Confirm rate targets + travel preferences.",
            "Activate for matching when jobs post.",
        ])

    return {
        "lane": lane,
        "bucket": bucket,
        "priority": priority,
        "next_steps": next_steps,
    }


def ready_to_work_pack_lmt(intake: Dict[str, Any]) -> Dict[str, Any]:
    """
    IMPORTANT: This is NOT a legal W-9 generator.
    It's a "Ready-to-work profile pack" that can be used to prefill forms later.
    We intentionally do NOT collect SSN in-app.
    """
    pack = {
        "profile": {
            "legal_name": intake.get("legal_name", ""),
            "preferred_name": intake.get("preferred_name", ""),
            "email": intake.get("email", ""),
            "phone": intake.get("phone", ""),
            "home_city": intake.get("home_city", ""),
            "home_state": intake.get("home_state", ""),
        },
        "work": {
            "worker_type": intake.get("worker_type", ""),
            "primary_role": intake.get("primary_role", ""),
            "secondary_roles": intake.get("secondary_roles", ""),
            "certifications": intake.get("certifications", ""),
            "availability_window": intake.get("availability_window", ""),
            "availability_notes": intake.get("availability_notes", ""),
            "travel_ok": intake.get("travel_ok", ""),
            "per_diem_required": intake.get("per_diem_required", ""),
            "rate_target": intake.get("rate_target", ""),
            "min_rate": intake.get("min_rate", ""),
        },
        "logistics": {
            "transportation_mode": intake.get("transportation_mode", ""),
            "truck_size": intake.get("truck_size", ""),
            "liftgate": intake.get("liftgate", ""),
        },
        "tax_profile": {
            "tax_ready": intake.get("tax_ready", ""),
            "business_name": intake.get("business_name", ""),
            "tax_classification": intake.get("tax_classification", ""),
            "ein_last4": intake.get("ein_last4", ""),
            "insurance_ready": intake.get("insurance_ready", ""),
        }
    }
    return pack


# =========================
# STRIPE ENV REQUIREMENTS
# =========================
def require_stripe_env():
    missing = []
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_PRICE_ID:
        missing.append("STRIPE_PRICE_ID")
    if not SUCCESS_URL or not (SUCCESS_URL.startswith("https://") or SUCCESS_URL.startswith("http://")):
        missing.append("SUCCESS_URL")
    if not CANCEL_URL or not (CANCEL_URL.startswith("https://") or CANCEL_URL.startswith("http://")):
        missing.append("CANCEL_URL")
    if missing:
        return JSONResponse({"error": "Missing/invalid environment variables", "missing": missing}, status_code=500)
    return None


# =========================
# CORE PAGES
# =========================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)


# =========================
# PUBLIC LEAD + PARTNER
# =========================
@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/lead")
def lead_submit(
    name: str = Form(...),
    email: str = Form(...),
    interest: str = Form(""),
    phone: str = Form(""),
    company: str = Form(""),
    message: str = Form(""),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (name, email, phone, company, interest, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, email, phone, company, interest, message, now_iso()))
    conn.commit()
    conn.close()
    return RedirectResponse("/lead/thanks", status_code=303)

@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return templates.TemplateResponse("lead_thanks.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/partner")
def partner_submit(
    name: str = Form(...),
    email: str = Form(...),
    company: str = Form(""),
    role: str = Form(""),
    product_type: str = Form(""),
    website: str = Form(""),
    regions: str = Form(""),
    message: str = Form(""),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, website, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, email, company, role, product_type, website, regions, message, now_iso()))
    conn.commit()
    conn.close()
    return RedirectResponse("/partner/thanks", status_code=303)

@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return templates.TemplateResponse("partner_thanks.html", {"request": request, "year": datetime.utcnow().year})


# =========================
# STRIPE CHECKOUT
# =========================
@app.get("/checkout")
def checkout(ref: Optional[str] = None):
    err = require_stripe_env()
    if err:
        return err

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
        )
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/success", response_class=HTMLResponse)
def success(request: Request, session_id: Optional[str] = None):
    token = None
    email = None
    dashboard_link = None

    if session_id and STRIPE_SECRET_KEY:
        try:
            s = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])
            details = s.get("customer_details") or {}
            email = (details.get("email") or "").strip().lower()

            customer_id = str(s.get("customer") or "")
            subscription_id = str(s.get("subscription") or "")

            if email:
                upsert_subscriber_active(email, customer_id, subscription_id)
                token = issue_magic_link(email, hours=24)
                base = str(request.base_url).rstrip("/")
                dashboard_link = f"{base}/dashboard?token={token}"

                if EMAIL_USER and EMAIL_PASS:
                    send_email(
                        email,
                        "Your Nautical Compass Access Link",
                        f"Welcome.\n\nYour access link (valid 24 hours):\n{dashboard_link}\n"
                    )

        except Exception as e:
            print("Success fetch failed:", e)

    return templates.TemplateResponse(
        "success.html",
        {"request": request, "token": token, "email": email, "dashboard_link": dashboard_link, "year": datetime.utcnow().year},
    )


@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request, "year": datetime.utcnow().year})


# =========================
# STRIPE WEBHOOK (PROD)
# =========================
@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Missing STRIPE_WEBHOOK_SECRET")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook signature error: {e}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = str(session.get("customer") or "")
        customer_email = (session.get("customer_details", {}) or {}).get("email")
        subscription_id = str(session.get("subscription") or "")

        if customer_email:
            customer_email = customer_email.strip().lower()
            upsert_subscriber_active(customer_email, customer_id, subscription_id)

            token = issue_magic_link(customer_email, hours=24)
            base = str(request.base_url).rstrip("/")
            link = f"{base}/dashboard?token={token}"

            if EMAIL_USER and EMAIL_PASS:
                send_email(
                    customer_email,
                    "Your Nautical Compass Access Link",
                    f"Welcome.\n\nYour access link (valid 24 hours):\n{link}\n"
                )

    if event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        sub_id = str(sub.get("id") or "")

        conn = db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE subscribers
            SET status='canceled', updated_at=?
            WHERE stripe_subscription_id=?
        """, (now_iso(), sub_id))
        conn.commit()
        conn.close()

    return {"received": True}


@app.post("/webhook/stripe")
async def stripe_webhook_alias(request: Request):
    return await stripe_webhook(request)


# =========================
# SUBSCRIBER DASH + NC INTAKE
# =========================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "email": email, "token": token, "year": datetime.utcnow().year},
    )


@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse(
        "intake_form.html",
        {"request": request, "email": email, "token": token, "year": datetime.utcnow().year},
    )


@app.post("/intake")
def submit_intake(
    token: str,
    name: str = Form(...),
    email: str = Form(...),
    service_requested: str = Form(...),
    notes: str = Form(""),
    injury: str = Form(""),
    wants: str = Form(""),
    defendant_type: str = Form(""),
    timeline: str = Form(""),
):
    subscriber_email, err = require_subscriber_token(token)
    if err:
        return err

    intake_obj = {
        "subscriber_email": subscriber_email,
        "name": name,
        "email": email,
        "service_requested": service_requested,
        "notes": notes or "",
        "injury": injury or "",
        "wants": wants or "",
        "defendant_type": defendant_type or "",
        "timeline": timeline or "",
    }

    flags = risk_flags_v1_nc(intake_obj)
    topics = spine_pick(service_requested)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (subscriber_email, name, email, service_requested, notes, facts_json, flags_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        subscriber_email,
        name,
        email,
        service_requested,
        notes or "",
        str(intake_obj),
        str(flags),
        now_iso(),
    ))
    intake_id = cur.lastrowid
    conn.commit()
    conn.close()

    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber: {subscriber_email}\n\n"
            f"Name: {name}\nEmail: {email}\nService: {service_requested}\n\n"
            f"Injury: {injury}\nWants: {wants}\nDefendant type: {defendant_type}\nTimeline: {timeline}\n\n"
            f"Notes:\n{notes}\n"
        )

    return RedirectResponse(f"/results?id={intake_id}&token={token}&mode=basic", status_code=303)


@app.get("/results", response_class=HTMLResponse)
def results(request: Request, id: int, token: str, mode: str = "basic"):
    subscriber_email, err = require_subscriber_token(token)
    if err:
        return err

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake WHERE id = ? LIMIT 1", (id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return HTMLResponse("Intake not found.", status_code=404)

    if row["subscriber_email"] != subscriber_email:
        return HTMLResponse("Unauthorized.", status_code=403)

    flags = risk_flags_v1_nc({
        "service_requested": row["service_requested"],
        "notes": row["notes"] or "",
        "injury": "",
        "wants": "",
    })

    topics = spine_pick(row["service_requested"])
    spine_blocks = []
    for t in topics:
        entry = LEGAL_SPINE.get(t)
        if entry:
            spine_blocks.append(entry)

    mode = (mode or "basic").lower().strip()
    if mode not in ("basic", "court"):
        mode = "basic"

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "token": token,
            "mode": mode,
            "intake_id": row["id"],
            "service_requested": row["service_requested"],
            "notes": row["notes"] or "",
            "flags": flags,
            "spine": spine_blocks,
            "year": datetime.utcnow().year,
        },
    )


# =========================
# AVPT CLIENT LANE (PRODUCTION COMPANY)
# =========================
@app.get("/avpt/client", response_class=HTMLResponse)
def avpt_client_form(request: Request):
    return templates.TemplateResponse("avpt_client_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/avpt/client")
def avpt_client_submit(
    company_name: str = Form(...),
    contact_name: str = Form(...),
    contact_email: str = Form(...),
    contact_phone: str = Form(""),

    event_name: str = Form(""),
    event_type: str = Form(""),
    venue_name: str = Form(""),
    venue_address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),

    load_in_date: str = Form(""),
    show_date: str = Form(""),
    load_out_date: str = Form(""),

    crew_counts: str = Form(""),
    gear_scope: str = Form(""),
    schedule_notes: str = Form(""),

    budget_range: str = Form(""),
    rate_expectation: str = Form(""),
    payment_terms: str = Form(""),

    point_of_contact_on_site: str = Form(""),
    safety_notes: str = Form(""),

    requires_coi: str = Form("No"),
    po_required: str = Form("No"),
):
    intake_obj = {
        "company_name": company_name,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "event_name": event_name,
        "event_type": event_type,
        "venue_name": venue_name,
        "venue_address": venue_address,
        "city": city,
        "state": state,
        "load_in_date": load_in_date,
        "show_date": show_date,
        "load_out_date": load_out_date,
        "crew_counts": crew_counts,
        "gear_scope": gear_scope,
        "schedule_notes": schedule_notes,
        "budget_range": budget_range,
        "rate_expectation": rate_expectation,
        "payment_terms": payment_terms,
        "point_of_contact_on_site": point_of_contact_on_site,
        "safety_notes": safety_notes,
        "requires_coi": requires_coi,
        "po_required": po_required,
    }

    flags = risk_flags_v1_avpt(intake_obj)
    routing = route_v1_avpt(intake_obj, flags)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO avpt_clients (
            company_name, contact_name, contact_email, contact_phone,
            event_name, event_type, venue_name, venue_address, city, state,
            load_in_date, show_date, load_out_date,
            crew_counts, gear_scope, schedule_notes,
            budget_range, rate_expectation, payment_terms,
            point_of_contact_on_site, safety_notes,
            requires_coi, po_required,
            routing_json, flags_json, created_at
        )
        VALUES (?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?)
    """, (
        company_name, contact_name, contact_email, contact_phone,
        event_name, event_type, venue_name, venue_address, city, state,
        load_in_date, show_date, load_out_date,
        crew_counts, gear_scope, schedule_notes,
        budget_range, rate_expectation, payment_terms,
        point_of_contact_on_site, safety_notes,
        requires_coi, po_required,
        str(routing), str(flags), now_iso()
    ))
    avpt_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Optional ops email
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "AVPT Client Intake Submitted",
            f"Company: {company_name}\nContact: {contact_name} ({contact_email})\n"
            f"Event: {event_name} / {event_type}\n"
            f"Venue: {venue_name}\nAddress: {venue_address}\n"
            f"Dates: Load-in={load_in_date} Show={show_date} Load-out={load_out_date}\n"
            f"Crew: {crew_counts}\nGear: {gear_scope}\nBudget: {budget_range}\n"
            f"Flags: {len(flags)}\nRouting: {routing}\n"
        )

    return RedirectResponse(f"/avpt/results?id={avpt_id}", status_code=303)


@app.get("/avpt/results", response_class=HTMLResponse)
def avpt_results(request: Request, id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM avpt_clients WHERE id = ? LIMIT 1", (id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return HTMLResponse("AVPT intake not found.", status_code=404)

    flags = []
    try:
        # stored as string; keep safe display
        flags = eval(row["flags_json"]) if row["flags_json"] else []
    except Exception:
        flags = []

    routing = {}
    try:
        routing = eval(row["routing_json"]) if row["routing_json"] else {}
    except Exception:
        routing = {}

    return templates.TemplateResponse(
        "results_avpt.html",
        {
            "request": request,
            "year": datetime.utcnow().year,
            "lane_title": "AVPT — Production Company Results",
            "id": row["id"],
            "summary": {
                "Company": row["company_name"],
                "Contact": f'{row["contact_name"]} ({row["contact_email"]})',
                "Show date": row["show_date"],
                "Venue address": row["venue_address"],
                "Crew counts": row["crew_counts"],
                "Budget range": row["budget_range"],
            },
            "flags": flags,
            "routing": routing,
            "next_url": "/avpt/client",
        }
    )


# =========================
# LMT WORKER LANE (LABOR/TECH)
# =========================
@app.get("/lmt/worker", response_class=HTMLResponse)
def lmt_worker_form(request: Request):
    return templates.TemplateResponse("lmt_worker_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/lmt/worker")
def lmt_worker_submit(
    legal_name: str = Form(...),
    preferred_name: str = Form(""),
    email: str = Form(...),
    phone: str = Form(...),
    home_city: str = Form(""),
    home_state: str = Form(""),

    worker_type: str = Form(""),
    primary_role: str = Form(""),
    secondary_roles: str = Form(""),
    certifications: str = Form(""),

    availability_window: str = Form(""),
    availability_notes: str = Form(""),

    transportation_mode: str = Form(""),
    truck_size: str = Form(""),
    liftgate: str = Form(""),

    travel_ok: str = Form(""),
    per_diem_required: str = Form(""),

    rate_target: str = Form(""),
    min_rate: str = Form(""),

    tax_ready: str = Form(""),
    business_name: str = Form(""),
    tax_classification: str = Form(""),
    ein_last4: str = Form(""),
    insurance_ready: str = Form(""),

    notes: str = Form(""),
):
    intake_obj = {
        "legal_name": legal_name,
        "preferred_name": preferred_name,
        "email": email,
        "phone": phone,
        "home_city": home_city,
        "home_state": home_state,
        "worker_type": worker_type,
        "primary_role": primary_role,
        "secondary_roles": secondary_roles,
        "certifications": certifications,
        "availability_window": availability_window,
        "availability_notes": availability_notes,
        "transportation_mode": transportation_mode,
        "truck_size": truck_size,
        "liftgate": liftgate,
        "travel_ok": travel_ok,
        "per_diem_required": per_diem_required,
        "rate_target": rate_target,
        "min_rate": min_rate,
        "tax_ready": tax_ready,
        "business_name": business_name,
        "tax_classification": tax_classification,
        "ein_last4": ein_last4,
        "insurance_ready": insurance_ready,
        "notes": notes,
    }

    flags = risk_flags_v1_lmt(intake_obj)
    routing = route_v1_lmt(intake_obj, flags)
    pack = ready_to_work_pack_lmt(intake_obj)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lmt_workers (
            legal_name, preferred_name, email, phone, home_city, home_state,
            worker_type, primary_role, secondary_roles, certifications,
            availability_window, availability_notes,
            transportation_mode, truck_size, liftgate,
            travel_ok, per_diem_required,
            rate_target, min_rate,
            tax_ready, business_name, tax_classification, ein_last4, insurance_ready,
            notes,
            routing_json, flags_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?, ?, ?,
                ?,
                ?, ?, ?)
    """, (
        legal_name, preferred_name, email, phone, home_city, home_state,
        worker_type, primary_role, secondary_roles, certifications,
        availability_window, availability_notes,
        transportation_mode, truck_size, liftgate,
        travel_ok, per_diem_required,
        rate_target, min_rate,
        tax_ready, business_name, tax_classification, ein_last4, insurance_ready,
        notes,
        str({"routing": routing, "pack": pack}), str(flags), now_iso()
    ))
    lmt_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Optional ops email
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "LMT Worker Intake Submitted",
            f"Legal name: {legal_name}\nEmail: {email}\nPhone: {phone}\n"
            f"Primary role: {primary_role}\nAvailability: {availability_window}\n"
            f"Transport: {transportation_mode} / {truck_size} / liftgate={liftgate}\n"
            f"Tax-ready: {tax_ready} / class={tax_classification}\n"
            f"Flags: {len(flags)}\nRouting: {routing}\n"
        )

    return RedirectResponse(f"/lmt/results?id={lmt_id}", status_code=303)


@app.get("/lmt/results", response_class=HTMLResponse)
def lmt_results(request: Request, id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM lmt_workers WHERE id = ? LIMIT 1", (id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return HTMLResponse("LMT intake not found.", status_code=404)

    flags = []
    try:
        flags = eval(row["flags_json"]) if row["flags_json"] else []
    except Exception:
        flags = []

    routing = {}
    pack = {}
    try:
        blob = eval(row["routing_json"]) if row["routing_json"] else {}
        routing = blob.get("routing", {})
        pack = blob.get("pack", {})
    except Exception:
        routing = {}
        pack = {}

    return templates.TemplateResponse(
        "results_lmt.html",
        {
            "request": request,
            "year": datetime.utcnow().year,
            "lane_title": "LMT — Labor/Tech Results",
            "id": row["id"],
            "summary": {
                "Legal name": row["legal_name"],
                "Email": row["email"],
                "Phone": row["phone"],
                "Primary role": row["primary_role"],
                "Availability": row["availability_window"],
                "Transport": f'{row["transportation_mode"]} / {row["truck_size"]} / liftgate={row["liftgate"]}',
                "Tax-ready": row["tax_ready"],
            },
            "flags": flags,
            "routing": routing,
            "pack": pack,
            "next_url": "/lmt/worker",
        }
    )


# =========================
# ADMIN JSON (quick sanity)
# =========================
@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id, subscriber_email, name, email, service_requested, created_at FROM intake ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}


# =========================
# DEV TOKEN ROUTE (TEST ACCESS)
# =========================
@app.get("/dev/generate-token")
def dev_generate_token(email: str, key: str, request: Request):
    if not DEV_TOKEN_ENABLED:
        return JSONResponse({"error": "Dev token route disabled"}, status_code=403)
    if not DEV_TOKEN_KEY:
        return JSONResponse({"error": "Dev token not set (missing DEV_TOKEN_KEY env var)"}, status_code=500)
    if _clean(key) != DEV_TOKEN_KEY:
        return JSONResponse({"error": "Bad key"}, status_code=401)

    email = _clean(email).lower()
    if not email or "@" not in email:
        return JSONResponse({"error": "Invalid email"}, status_code=400)

    upsert_subscriber_active(email, "", "")
    token = issue_magic_link(email, hours=24)

    base = str(request.base_url).rstrip("/")
    return {
        "email": email,
        "token": token,
        "dashboard": f"{base}/dashboard?token={token}",
        "intake_form": f"{base}/intake-form?token={token}",
    }
