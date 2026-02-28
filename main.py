import os
import sqlite3
import smtplib
import hashlib
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr

# ============================================================
# PATHS (LOCKED)
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nc.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# ============================================================
# APP
# ============================================================
app = FastAPI(title="Nautical Compass Intake")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================
# CLEANERS / ENV HELPERS
# ============================================================
def _clean(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", "").strip()


def _clean_url(s: str) -> str:
    s = _clean(s)
    # DO UI sometimes injects "Value: https://..."
    if s.lower().startswith("value:"):
        s = s.split(":", 1)[1].strip()
    return s


def _require_valid_url(name: str, url: str) -> str:
    url = _clean_url(url)
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"{name} is not a valid URL (must start with http:// or https://)")
    return url


# ============================================================
# STRIPE CONFIG
# ============================================================
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

# Sponsor tier (optional)
STRIPE_SPONSOR_PRICE_ID = _clean(os.getenv("STRIPE_SPONSOR_PRICE_ID", ""))

try:
    SUCCESS_URL = _require_valid_url("SUCCESS_URL", os.getenv("SUCCESS_URL", ""))
    CANCEL_URL = _require_valid_url("CANCEL_URL", os.getenv("CANCEL_URL", ""))
except Exception as e:
    # Keep app alive even if URLs wrong; endpoints will return error
    SUCCESS_URL = _clean_url(os.getenv("SUCCESS_URL", ""))
    CANCEL_URL = _clean_url(os.getenv("CANCEL_URL", ""))
    STARTUP_URL_ERROR = str(e)
else:
    STARTUP_URL_ERROR = ""

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


# ============================================================
# EMAIL CONFIG (OPTIONAL)
# ============================================================
# (Keep your existing EMAIL_USER / EMAIL_PASS if you want email notifications)
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))

# If you later switch to Mailgun SMTP, you can add these env vars and the app will use them.
SMTP_HOST = _clean(os.getenv("SMTP_HOST", "")) or "smtp.gmail.com"
SMTP_PORT = int(_clean(os.getenv("SMTP_PORT", "")) or "465")

# ============================================================
# ADMIN / DEV KEYS
# ============================================================
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))


def require_admin(k: Optional[str]):
    k = _clean(k or "")
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set in environment.")
    if k != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized (bad admin key).")


# ============================================================
# DB HELPERS
# ============================================================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso():
    return datetime.utcnow().isoformat()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ============================================================
# MODELS — NC / LEAD / PARTNER / CONTRIBUTOR
# ============================================================
class IntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: str | None = None


class LeadForm(BaseModel):
    name: str
    email: str
    interest: str = ""
    phone: str = ""
    company: str = ""
    message: str = ""


class PartnerForm(BaseModel):
    name: str
    email: str
    company: str = ""
    role: str = ""
    product_type: str = ""
    website: str = ""
    regions: str = ""
    message: str = ""


class ContributorForm(BaseModel):
    name: str
    email: EmailStr
    phone: str = ""
    company: str = ""
    website: str = ""

    primary_role: str
    contribution_track: str
    position_interest: str = ""
    comp_plan: str = ""

    # user requested spelling
    director_owner: str = "Duece"

    assets: str = ""
    regions: str = ""
    capacity: str = ""
    alignment: str = ""
    message: str = ""

    fit_access: str = ""
    fit_build_goal: str = ""
    fit_opportunity: str = ""
    fit_authority: str = ""
    fit_lane: str = ""
    fit_no_conditions: str = ""
    fit_visibility: str = ""
    fit_why_you: str = ""


# ============================================================
# MODELS — AVPT CLIENT JOB / LMT WORKER PROFILE (NEW)
# ============================================================
class AVPTJobRequest(BaseModel):
    company_name: str
    contact_name: str
    contact_email: EmailStr
    contact_phone: str = ""

    job_title: str
    city: str
    state: str
    venue: str = ""
    address: str = ""

    date: str  # keep simple (YYYY-MM-DD from UI)
    call_time: str = ""  # "07:00"
    end_time: str = ""   # "19:00"

    department: str = ""  # audio/video/lighting/led/rigging/etc
    roles_needed: str     # free text OR "A1(2), V1(1)..."
    headcount: int = 1

    rate_target: str = ""     # "$45/hr"
    budget_notes: str = ""    # free text

    gear_required: str = ""   # free text
    truck_needed: str = ""    # none / sprinter / 16ft / 26ft / tractor
    liftgate_required: str = ""  # yes/no
    parking_dock: str = ""    # notes

    certifications_required: str = ""  # OSHA10, Forklift, ETC
    union_house: str = ""      # optional
    notes: str = ""


class LMTWorkerProfile(BaseModel):
    name: str
    email: EmailStr
    phone: str = ""

    home_city: str
    home_state: str
    travel_radius_miles: int = 25

    primary_roles: str  # "A2, V1, LED Tech"
    secondary_roles: str = ""

    availability_next_7_days: str = ""  # free text "Mon/Tue open; Wed after 2pm"
    transportation: str = ""            # "metro", "car", "truck"
    truck_size: str = ""               # none/sprinter/16ft/26ft
    liftgate: str = ""                 # yes/no
    tools_certifications: str = ""     # "OSHA10, Forklift"
    preferred_rate: str = ""           # "$45/hr"
    notes: str = ""


# ============================================================
# TABLES
# ============================================================
def init_db():
    conn = db()
    cur = conn.cursor()

    # NC intakes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS intake (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            service_requested TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # public lead capture
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

    # partner/manufacturer intake
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

    # subscribers + magic links
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS magic_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # contributors
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            company TEXT,
            website TEXT,

            primary_role TEXT NOT NULL,

            contribution_track TEXT NOT NULL,
            position_interest TEXT,
            comp_plan TEXT,
            director_owner TEXT,

            assets TEXT,
            regions TEXT,
            capacity TEXT,
            alignment TEXT,
            message TEXT,

            fit_access TEXT,
            fit_build_goal TEXT,
            fit_opportunity TEXT,
            fit_authority TEXT,
            fit_lane TEXT,
            fit_no_conditions TEXT,
            fit_visibility TEXT,
            fit_why_you TEXT,

            score INTEGER NOT NULL DEFAULT 0,
            rail TEXT NOT NULL DEFAULT 'triage',
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL
        )
    """)

    # -------------------------
    # NEW: AVPT client jobs
    # -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS avpt_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            contact_phone TEXT,

            job_title TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            venue TEXT,
            address TEXT,

            date TEXT,
            call_time TEXT,
            end_time TEXT,

            department TEXT,
            roles_needed TEXT NOT NULL,
            headcount INTEGER NOT NULL DEFAULT 1,

            rate_target TEXT,
            budget_notes TEXT,

            gear_required TEXT,
            truck_needed TEXT,
            liftgate_required TEXT,
            parking_dock TEXT,

            certifications_required TEXT,
            union_house TEXT,
            notes TEXT,

            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL
        )
    """)

    # -------------------------
    # NEW: LMT worker profiles
    # -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lmt_workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,

            home_city TEXT NOT NULL,
            home_state TEXT NOT NULL,
            travel_radius_miles INTEGER NOT NULL DEFAULT 25,

            primary_roles TEXT NOT NULL,
            secondary_roles TEXT,

            availability_next_7_days TEXT,
            transportation TEXT,
            truck_size TEXT,
            liftgate TEXT,
            tools_certifications TEXT,
            preferred_rate TEXT,
            notes TEXT,

            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ============================================================
# EMAIL SENDER
# ============================================================
def send_email(to_email: str, subject: str, body: str):
    if not (EMAIL_USER and EMAIL_PASS):
        return

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg.set_content(body)

        # Gmail SSL default, but can be swapped by env vars
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.starttls()
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)

    except Exception as e:
        print("Email failed:", e)


# ============================================================
# MAGIC LINKS + SUBSCRIBERS
# ============================================================
def issue_magic_link(email: str, hours: int = 24) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = sha256(token)
    expires = (datetime.utcnow() + timedelta(hours=hours)).isoformat()

    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO magic_links (email, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (email, token_hash, expires, now_iso())
    )
    conn.commit()
    conn.close()
    return token


def validate_magic_link(token: str) -> str | None:
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
    cur.execute("SELECT status FROM subscribers WHERE email = ? LIMIT 1", (email,))
    row = cur.fetchone()
    conn.close()
    return bool(row) and row["status"] == "active"


def upsert_subscriber_active(email: str, customer_id: str = "", subscription_id: str = ""):
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


def require_subscriber_token(token: str | None):
    if not token:
        return None, HTMLResponse("Missing token.", status_code=401)

    email = validate_magic_link(token)
    if not email:
        return None, HTMLResponse("Invalid or expired link.", status_code=401)

    if not is_active_subscriber(email):
        return None, HTMLResponse("Subscription not active.", status_code=403)

    return email, None


# ============================================================
# CONTRIBUTOR SCORING / RAIL ASSIGNMENT
# ============================================================
def _score_contributor(f: ContributorForm) -> int:
    score = 0
    track = (f.contribution_track or "").strip().lower()

    track_weights = {
        "ecosystem_staff": 18,
        "sales_growth": 18,
        "builder_operator": 16,
        "partner_vendor": 14,
        "hardware_supply": 16,
        "capital_sponsor": 14,
        "advisor_specialist": 10,
        "not_sure": 8,
    }
    score += track_weights.get(track, 10)

    comp = (f.comp_plan or "").strip().lower()
    if "residual" in comp:
        score += 10
    elif "commission" in comp:
        score += 10
    elif "hourly" in comp:
        score += 6
    elif "equity" in comp or "revshare" in comp:
        score += 8

    if f.assets and len(f.assets.strip()) > 10:
        score += 10
    if f.website and len(f.website.strip()) > 6:
        score += 6
    if f.company and len(f.company.strip()) > 2:
        score += 4

    fit_fields = [
        f.fit_access, f.fit_build_goal, f.fit_opportunity, f.fit_authority,
        f.fit_lane, f.fit_no_conditions, f.fit_visibility, f.fit_why_you
    ]
    filled = sum(1 for x in fit_fields if x and str(x).strip())
    score += min(16, filled * 2)

    auth = (f.fit_authority or "").lower().strip()
    if auth == "owner_exec":
        score += 10
    elif auth == "manager_influence":
        score += 6
    elif auth == "partial":
        score += 3

    return int(score)


def _assign_rail(f: ContributorForm, score: int) -> str:
    track = (f.contribution_track or "").strip().lower()
    pos = (f.position_interest or "").strip().lower()
    lane = (f.fit_lane or "").strip().lower()

    if score >= 70:
        if track == "sales_growth" or lane == "sales" or "sales" in pos or "closer" in pos:
            return "sales_priority"
        if track == "ecosystem_staff" or "intake" in pos or "ops" in pos or "client" in pos:
            return "staff_priority"
        if track == "hardware_supply" or lane == "hardware":
            return "hardware_supply"
        if track == "capital_sponsor" or lane == "finance":
            return "capital"
        return "priority"

    if score >= 45:
        if track == "sales_growth":
            return "sales_pool"
        if track == "ecosystem_staff":
            return "staff_pool"
        if track in ("partner_vendor", "hardware_supply"):
            return "bd_followup"
        return "review"

    return "triage"


# ============================================================
# MATCHING V1 — AVPT JOB ↔ LMT WORKERS
# ============================================================
def _norm(s: str) -> str:
    return _clean(s).lower()


def _contains_any(haystack: str, needles: List[str]) -> bool:
    h = _norm(haystack)
    return any(n in h for n in needles)


def _score_worker_for_job(job: sqlite3.Row, w: sqlite3.Row) -> Tuple[int, List[str]]:
    """
    Simple + explainable scoring. This is intentionally not "AI" yet.
    It's transparent, predictable, and easy to upgrade.
    """
    score = 0
    reasons = []

    # Location (same state)
    if _norm(job["state"]) == _norm(w["home_state"]):
        score += 18
        reasons.append("Same state match")
    else:
        score += 6
        reasons.append("Out-of-state (possible travel)")

    # City proximity heuristic (string)
    if _norm(job["city"]) == _norm(w["home_city"]):
        score += 10
        reasons.append("Same city match")

    # Role match heuristic
    roles_needed = _norm(job["roles_needed"])
    w_roles = _norm(w["primary_roles"] + " " + (w["secondary_roles"] or ""))

    # Basic keywords: A1/A2/V1/V2/LED/Rig/Stagehand/Carp/Audio/Video
    role_hits = 0
    for key in ["a1", "a2", "v1", "v2", "led", "rig", "rigger", "stagehand", "carp", "audio", "video", "lx", "lighting", "cam", "broadcast"]:
        if key in roles_needed and key in w_roles:
            role_hits += 1

    if role_hits >= 2:
        score += 25
        reasons.append("Strong role alignment")
    elif role_hits == 1:
        score += 14
        reasons.append("Partial role alignment")
    else:
        score += 4
        reasons.append("Role alignment unknown (manual review)")

    # Availability (non-empty = small boost; later you’ll parse it)
    if _clean(w["availability_next_7_days"]):
        score += 8
        reasons.append("Availability provided")

    # Certifications vs required
    if _clean(job["certifications_required"]):
        req = _norm(job["certifications_required"])
        have = _norm(w["tools_certifications"] or "")
        if req and any(x in have for x in req.split()):
            score += 10
            reasons.append("Certifications likely match")
        else:
            score += 2
            reasons.append("Certifications unclear")

    # Truck / liftgate preference if job requires
    if _norm(job["liftgate_required"]) in ("yes", "required", "true"):
        if _norm(w["liftgate"]) in ("yes", "true"):
            score += 8
            reasons.append("Has liftgate capability")
        else:
            reasons.append("Liftgate required (worker may not have)")

    if _clean(job["truck_needed"]):
        tn = _norm(job["truck_needed"])
        ws = _norm(w["truck_size"] or "")
        if tn and tn in ws:
            score += 7
            reasons.append("Truck size aligns")

    # Rate info present
    if _clean(w["preferred_rate"]):
        score += 4
        reasons.append("Rate provided")

    return score, reasons


def get_job(job_id: int) -> sqlite3.Row | None:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM avpt_jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    conn.close()
    return row


# ============================================================
# FAVICON
# ============================================================
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)


# ============================================================
# PUBLIC PAGES (NC)
# ============================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/lead")
def lead_submit(form: LeadForm):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (name, email, phone, company, interest, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (form.name, form.email, form.phone, form.company, form.interest, form.message, now_iso()))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/lead/thanks", status_code=303)


@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return templates.TemplateResponse("lead_thanks.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/partner")
def partner_submit(form: PartnerForm):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, website, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (form.name, form.email, form.company, form.role, form.product_type, form.website, form.regions, form.message, now_iso()))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/partner/thanks", status_code=303)


@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return templates.TemplateResponse("partner_thanks.html", {"request": request, "year": datetime.utcnow().year})


# ============================================================
# SUBSCRIBER INTAKE (NC)
# ============================================================
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("intake_form.html", {"request": request, "email": email, "token": token, "year": datetime.utcnow().year})


@app.post("/intake")
def submit_intake(form: IntakeForm, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (form.name, form.email, form.service_requested, form.notes or "", now_iso()))
    conn.commit()
    conn.close()

    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber: {email}\n\nName: {form.name}\nEmail: {form.email}\nService: {form.service_requested}\nNotes: {form.notes}"
        )

    return RedirectResponse(url=f"/dashboard?token={token}", status_code=303)


@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}


# ============================================================
# STRIPE CHECKOUT (NC)
# ============================================================
def require_stripe_env():
    missing = []
    if STARTUP_URL_ERROR:
        return JSONResponse({"error": STARTUP_URL_ERROR, "hint": "Fix SUCCESS_URL and CANCEL_URL env vars to valid https:// URLs."}, status_code=500)
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_PRICE_ID:
        missing.append("STRIPE_PRICE_ID")
    if not SUCCESS_URL:
        missing.append("SUCCESS_URL")
    if not CANCEL_URL:
        missing.append("CANCEL_URL")
    if missing:
        return JSONResponse({"error": "Missing environment variables", "missing": missing}, status_code=500)
    return None


@app.get("/checkout")
def checkout(ref: str | None = None):
    err = require_stripe_env()
    if err:
        return err

    # Store ref in Stripe metadata (for later commission engine)
    metadata = {}
    if ref:
        metadata["ref"] = _clean(ref)

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
            metadata=metadata if metadata else None,
        )
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/success", response_class=HTMLResponse)
def success(request: Request, session_id: str | None = None):
    token = None
    email = None
    dashboard_link = None

    # If Stripe is configured and session_id exists, generate access link immediately
    if session_id and STRIPE_SECRET_KEY:
        try:
            s = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])
            if s:
                details = s.get("customer_details") or {}
                email = details.get("email")

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
            print("Success page Stripe fetch failed:", e)

    return templates.TemplateResponse(
        "success.html",
        {"request": request, "token": token, "email": email, "dashboard_link": dashboard_link, "year": datetime.utcnow().year}
    )


@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request, "year": datetime.utcnow().year})


# ============================================================
# STRIPE WEBHOOK (NC)
# ============================================================
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


# ============================================================
# DASHBOARD (SUBSCRIBER)
# ============================================================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email, "token": token, "year": datetime.utcnow().year})


# ============================================================
# CONTRIBUTOR INTAKE + ADMIN
# ============================================================
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/contributor")
def submit_contributor(form: ContributorForm):
    score = _score_contributor(form)
    rail = _assign_rail(form, score)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contributors (
            name, email, phone, company, website,
            primary_role,
            contribution_track, position_interest, comp_plan, director_owner,
            assets, regions, capacity, alignment, message,
            fit_access, fit_build_goal, fit_opportunity, fit_authority,
            fit_lane, fit_no_conditions, fit_visibility, fit_why_you,
            score, rail, status, created_at
        )
        VALUES (?, ?, ?, ?, ?,
                ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?)
    """, (
        form.name, str(form.email), form.phone, form.company, form.website,
        form.primary_role,
        form.contribution_track, form.position_interest, form.comp_plan, form.director_owner,
        form.assets, form.regions, form.capacity, form.alignment, form.message,
        form.fit_access, form.fit_build_goal, form.fit_opportunity, form.fit_authority,
        form.fit_lane, form.fit_no_conditions, form.fit_visibility, form.fit_why_you,
        score, rail, "new", now_iso()
    ))
    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        "contributor_thanks.html",
        {"request": Request, "year": datetime.utcnow().year, "score": score, "rail": rail}
    )


@app.get("/admin/contributors-dashboard", response_class=HTMLResponse)
def contributors_dashboard(
    request: Request,
    k: Optional[str] = None,
    key: Optional[str] = None,
    rail: Optional[str] = None,
    min_score: Optional[int] = None,
    track: Optional[str] = None,
):
    # accept either k or key
    admin_k = k or key
    require_admin(admin_k)

    conn = db()
    cur = conn.cursor()

    query = "SELECT * FROM contributors WHERE 1=1"
    params = []

    if rail:
        query += " AND rail = ?"
        params.append(rail)

    if min_score is not None:
        query += " AND score >= ?"
        params.append(min_score)

    if track:
        query += " AND contribution_track = ?"
        params.append(track)

    query += " ORDER BY score DESC"

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "contributors_dashboard.html",
        {"request": request, "contributors": rows, "rail": rail, "min_score": min_score, "track": track, "k": admin_k, "year": datetime.utcnow().year},
    )


@app.post("/admin/contributor-status")
def update_contributor_status(id: int, status: str, k: Optional[str] = None, key: Optional[str] = None):
    require_admin(k or key)

    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, id))
    conn.commit()
    conn.close()
    return {"ok": True}


# ============================================================
# ADMIN: LEADS DASHBOARD (VIEW)
# ============================================================
@app.get("/admin/leads-dashboard", response_class=HTMLResponse)
def leads_dashboard(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    require_admin(k or key)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 500")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("leads_dashboard.html", {"request": request, "leads": rows, "k": (k or key), "year": datetime.utcnow().year})


# ============================================================
# DEV TOKEN ROUTE (TEST SUBSCRIBER ACCESS WITHOUT PAYING)
# ============================================================
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

    # Mark active so the link works
    upsert_subscriber_active(email, "", "")
    token = issue_magic_link(email, hours=24)

    base = str(request.base_url).rstrip("/")
    return {
        "email": email,
        "token": token,
        "dashboard": f"{base}/dashboard?token={token}",
        "intake_form": f"{base}/intake-form?token={token}",
    }


# ============================================================
# ============================================================
# NEW LANE 1: AVPT CLIENT JOB REQUEST (AVPT client)
# ============================================================
@app.get("/avpt", response_class=HTMLResponse)
def avpt_home(request: Request):
    # Simple landing that routes to request
    return templates.TemplateResponse("avpt_home.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/avpt/request", response_class=HTMLResponse)
def avpt_request_page(request: Request):
    return templates.TemplateResponse("avpt_request.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/avpt/request")
def avpt_request_submit(form: AVPTJobRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO avpt_jobs (
            company_name, contact_name, contact_email, contact_phone,
            job_title, city, state, venue, address,
            date, call_time, end_time,
            department, roles_needed, headcount,
            rate_target, budget_notes,
            gear_required, truck_needed, liftgate_required, parking_dock,
            certifications_required, union_house, notes,
            status, created_at
        ) VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            'new', ?
        )
    """, (
        form.company_name, form.contact_name, str(form.contact_email), form.contact_phone,
        form.job_title, form.city, form.state, form.venue, form.address,
        form.date, form.call_time, form.end_time,
        form.department, form.roles_needed, int(form.headcount),
        form.rate_target, form.budget_notes,
        form.gear_required, form.truck_needed, form.liftgate_required, form.parking_dock,
        form.certifications_required, form.union_house, form.notes,
        now_iso()
    ))
    job_id = cur.lastrowid
    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/avpt/results?job_id={job_id}", status_code=303)


@app.get("/avpt/results", response_class=HTMLResponse)
def avpt_results(request: Request, job_id: int):
    job = get_job(job_id)
    if not job:
        return HTMLResponse("Job not found.", status_code=404)

    return templates.TemplateResponse(
        "avpt_results.html",
        {"request": request, "job": dict(job), "job_id": job_id, "year": datetime.utcnow().year}
    )


@app.get("/avpt/matches", response_class=HTMLResponse)
def avpt_matches(request: Request, job_id: int):
    job = get_job(job_id)
    if not job:
        return HTMLResponse("Job not found.", status_code=404)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM lmt_workers WHERE status='active' ORDER BY id DESC")
    workers = cur.fetchall()
    conn.close()

    scored = []
    for w in workers:
        s, reasons = _score_worker_for_job(job, w)
        scored.append({
            "score": s,
            "reasons": reasons,
            "worker": dict(w),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    # Only show top 25 to keep it clean
    top = scored[:25]

    return templates.TemplateResponse(
        "avpt_matches.html",
        {
            "request": request,
            "job": dict(job),
            "job_id": job_id,
            "matches": top,
            "year": datetime.utcnow().year
        }
    )


# ============================================================
# NEW LANE 2: LMT WORKER PROFILE (LMT worker)
# ============================================================
@app.get("/lmt", response_class=HTMLResponse)
def lmt_home(request: Request):
    return templates.TemplateResponse("lmt_home.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/lmt/worker", response_class=HTMLResponse)
def lmt_worker_page(request: Request):
    return templates.TemplateResponse("lmt_worker.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/lmt/worker")
def lmt_worker_submit(form: LMTWorkerProfile):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO lmt_workers (
            name, email, phone,
            home_city, home_state, travel_radius_miles,
            primary_roles, secondary_roles,
            availability_next_7_days, transportation, truck_size, liftgate,
            tools_certifications, preferred_rate, notes,
            status, created_at
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            'active', ?
        )
    """, (
        form.name, str(form.email), form.phone,
        form.home_city, form.home_state, int(form.travel_radius_miles),
        form.primary_roles, form.secondary_roles,
        form.availability_next_7_days, form.transportation, form.truck_size, form.liftgate,
        form.tools_certifications, form.preferred_rate, form.notes,
        now_iso()
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(url="/lmt/worker/thanks", status_code=303)


@app.get("/lmt/worker/thanks", response_class=HTMLResponse)
def lmt_worker_thanks(request: Request):
    return templates.TemplateResponse("lmt_worker_thanks.html", {"request": request, "year": datetime.utcnow().year})


# ============================================================
# DONE
# ============================================================
