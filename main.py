# main.py — Nautical Compass (NC) unified app
# FULL FILE (replace your entire main.py with this)

import os
import re
import sqlite3
import smtplib
import hashlib
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, List, Dict, Any

import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr


# --------------------
# Paths (LOCKED)
# --------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nc.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# --------------------
# App
# --------------------
app = FastAPI(title="Nautical Compass Intake")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --------------------
# Helpers
# --------------------
def now_iso() -> str:
    return datetime.utcnow().isoformat()

def _clean(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", "").strip()

def _clean_url(s: str) -> str:
    s = _clean(s)
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

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def is_truthy(v: str) -> bool:
    return _clean(v).lower() in ("1", "true", "yes", "y", "on")

def require_admin(k: str | None):
    admin_key = _clean(os.getenv("ADMIN_KEY", ""))
    if not admin_key:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set")
    if not k or _clean(k) != admin_key:
        raise HTTPException(status_code=401, detail="Admin key missing/invalid")

def get_admin_k(request: Request) -> str:
    # supports ?k= or ?key=
    qp = request.query_params
    return (qp.get("k") or qp.get("key") or "").strip()

# --------------------
# Stripe Config
# --------------------
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

# Sponsor SKU (optional)
STRIPE_SPONSOR_PRICE_ID = _clean(os.getenv("STRIPE_SPONSOR_PRICE_ID", ""))

try:
    SUCCESS_URL = _require_valid_url("SUCCESS_URL", os.getenv("SUCCESS_URL", ""))
    CANCEL_URL = _require_valid_url("CANCEL_URL", os.getenv("CANCEL_URL", ""))
except Exception as e:
    SUCCESS_URL = _clean_url(os.getenv("SUCCESS_URL", ""))
    CANCEL_URL = _clean_url(os.getenv("CANCEL_URL", ""))
    STARTUP_URL_ERROR = str(e)
else:
    STARTUP_URL_ERROR = ""

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# --------------------
# Email (optional)
# --------------------
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))

SMTP_HOST = _clean(os.getenv("SMTP_HOST", ""))  # optional override
SMTP_PORT = _clean(os.getenv("SMTP_PORT", ""))  # optional override

def send_email(to_email: str, subject: str, body: str):
    if not (EMAIL_USER and EMAIL_PASS):
        return

    host = SMTP_HOST or "smtp.gmail.com"
    port = int(SMTP_PORT) if SMTP_PORT.isdigit() else 465

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg.set_content(body)

        # default SSL (gmail style)
        if port == 465:
            with smtplib.SMTP_SSL(host, port) as smtp:
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as smtp:
                smtp.starttls()
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)

# --------------------
# DB Init
# --------------------
def init_db():
    conn = db()
    cur = conn.cursor()

    # Public leads + partner
    cur.execute("""
      CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        interest TEXT,
        phone TEXT,
        company TEXT,
        message TEXT,
        created_at TEXT NOT NULL
      )
    """)

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

    # Subscribers + magic links
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

    # Legal subscriber intake
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

    # Contributors intake
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

    # People (operators/staff)
    cur.execute("""
      CREATE TABLE IF NOT EXISTS people (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        role TEXT NOT NULL,         -- 'director' | 'operator' | 'staff'
        ref_code TEXT UNIQUE,       -- e.g. OPABCDE, DEUC46E
        parent_id INTEGER,          -- operator parent (e.g. Duece id)
        created_at TEXT NOT NULL
      )
    """)

    # AVPT Production requests (“jobs”)
    cur.execute("""
      CREATE TABLE IF NOT EXISTS avpt_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        contact_name TEXT NOT NULL,
        contact_email TEXT NOT NULL,
        contact_phone TEXT,
        city TEXT,
        state TEXT,
        venue TEXT,
        show_type TEXT,
        load_in_date TEXT,
        load_out_date TEXT,
        call_time TEXT,
        headcount_needed INTEGER,
        roles_needed TEXT,
        truck_size TEXT,
        liftgate TEXT,
        power_notes TEXT,
        union_terms TEXT,
        budget_notes TEXT,
        additional_notes TEXT,

        risk_flags TEXT,            -- JSON string
        routed_to TEXT,             -- lane/rail
        created_at TEXT NOT NULL
      )
    """)

    # LMT Workers (“labor intake”)
    cur.execute("""
      CREATE TABLE IF NOT EXISTS lmt_workers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        city TEXT,
        state TEXT,
        primary_role TEXT,
        skills TEXT,
        certs TEXT,
        has_llc TEXT,
        has_insurance TEXT,
        travel_ok TEXT,
        transportation TEXT,
        availability TEXT,
        union_member TEXT,
        pay_expectation TEXT,
        notes TEXT,

        risk_flags TEXT,            -- JSON string
        routed_to TEXT,             -- lane/rail
        created_at TEXT NOT NULL
      )
    """)

    conn.commit()
    conn.close()

init_db()

# --------------------
# Magic Links
# --------------------
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

# --------------------
# Referral helpers
# --------------------
def make_ref_code(prefix: str) -> str:
    # 5 chars base32-ish
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "".join(secrets.choice(alphabet) for _ in range(5))
    return f"{prefix}{body}"

# --------------------
# Risk Flags v1 (simple + expandable)
# --------------------
def add_flag(flags: List[Dict[str, Any]], code: str, severity: str, title: str, why: str, fix: str):
    flags.append({
        "code": code,
        "severity": severity,   # "low" | "med" | "high"
        "title": title,
        "why": why,
        "fix": fix,
    })

def risk_flags_production(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []

    headcount = payload.get("headcount_needed")
    if headcount is not None:
        try:
            headcount = int(headcount)
        except:
            headcount = None

    if not _clean(payload.get("roles_needed", "")):
        add_flag(flags, "ROLES_MISSING", "high",
                 "Roles not specified",
                 "You didn't list roles needed (A1, A2, V1, Stagehands, etc.).",
                 "List roles + quantity so dispatch can match correctly.")

    if headcount is None or headcount <= 0:
        add_flag(flags, "HEADCOUNT_MISSING", "high",
                 "Crew size missing",
                 "Headcount wasn't provided or is invalid.",
                 "Enter a headcount estimate (even a range).")

    if not _clean(payload.get("load_in_date", "")):
        add_flag(flags, "DATES_MISSING", "high",
                 "Dates missing",
                 "Load-in date is missing. Scheduling can't lock without it.",
                 "Add load-in/load-out dates (or at least start date).")

    if _clean(payload.get("liftgate", "")).lower() in ("unknown", "not sure", ""):
        add_flag(flags, "LIFTGATE_UNKNOWN", "med",
                 "Liftgate unknown",
                 "Truck/liftgate needs impact load-in time + labor planning.",
                 "Confirm truck type and whether liftgate is required.")

    if not _clean(payload.get("city", "")) or not _clean(payload.get("state", "")):
        add_flag(flags, "LOCATION_WEAK", "med",
                 "Location incomplete",
                 "City/State missing makes dispatch slower.",
                 "Add City + State (venue optional if undisclosed).")

    # Union terms clarity
    if _clean(payload.get("union_terms", "")).lower() in ("yes", "union", "required"):
        add_flag(flags, "UNION_TERMS", "low",
                 "Union terms indicated",
                 "Union jurisdiction may affect call rules and hiring constraints.",
                 "Confirm whether union labor is required and any venue rules.")

    # Budget signals
    budget = _clean(payload.get("budget_notes", "")).lower()
    if budget and any(x in budget for x in ["low", "tight", "cheap", "no budget"]):
        add_flag(flags, "BUDGET_TIGHT", "med",
                 "Budget appears tight",
                 "Budget language suggests rate conflict risk.",
                 "Confirm target rates; if constrained, reduce scope or adjust schedule.")

    return flags

def risk_flags_labor(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []

    # paperwork readiness (asked in a non-tax way)
    has_llc = _clean(payload.get("has_llc", "")).lower()
    has_ins = _clean(payload.get("has_insurance", "")).lower()

    if has_llc in ("no", "n"):
        add_flag(flags, "NO_LLC", "med",
                 "Business entity not set",
                 "Some clients require LLC/sole-prop setup for vendor onboarding.",
                 "We can help you set up an LLC/sole prop and store it in profile.")

    if has_ins in ("no", "n"):
        add_flag(flags, "NO_INSURANCE", "high",
                 "Insurance missing",
                 "Some venues/clients require COI/pro insurance for higher-tier calls.",
                 "Upgrade to VIP coverage path or add COI before premium dispatch.")

    # transport choice
    transport = _clean(payload.get("transportation", "")).lower()
    if transport in ("", "unknown"):
        add_flag(flags, "TRANSPORT_UNKNOWN", "low",
                 "Transportation not specified",
                 "Dispatch needs to know if you’re metro/car/ride-share.",
                 "Select car / metro / both so dispatch can route correctly.")
    if transport == "metro":
        add_flag(flags, "METRO_LIMITS", "low",
                 "Metro-only noted",
                 "Metro is strong in DMV but has limits for late-night load-outs.",
                 "Mark whether you can do late nights + how you get home.")

    # availability
    availability = _clean(payload.get("availability", ""))
    if not availability:
        add_flag(flags, "AVAIL_MISSING", "high",
                 "Availability missing",
                 "Clients need availability to staff you. No schedule = no dispatch.",
                 "Set your next 7-day availability (like union call-in).")

    # certs
    certs = _clean(payload.get("certs", ""))
    if not certs:
        add_flag(flags, "CERTS_UNKNOWN", "med",
                 "Certifications not listed",
                 "Certs help you qualify for premium calls and reduce risk.",
                 "Add certs (OSHA, lift, rigging, Dante, etc.) or mark 'None'.")

    return flags

def route_lane_by_flags(flags: List[Dict[str, Any]]) -> str:
    # simple routing: any high severity => priority review
    if any(f["severity"] == "high" for f in flags):
        return "priority_review"
    if any(f["severity"] == "med" for f in flags):
        return "review"
    return "ready"

# --------------------
# Models (JSON-friendly; HTML forms also work via Request.form())
# --------------------
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

class CreateOperator(BaseModel):
    name: str
    email: EmailStr

# --------------------
# Contributor scoring + rail assignment
# --------------------
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

# --------------------
# Pages — Core navigation
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # index.html should be your professional “who we are / industries / why we exist”
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/hall", response_class=HTMLResponse)
def hall(request: Request):
    # NEW cinematic “doors” page
    return templates.TemplateResponse("hall.html", {"request": request, "year": datetime.utcnow().year})

# --------------------
# Public Lead Intake
# --------------------
@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/lead")
async def lead_submit(request: Request):
    form = await request.form()
    name = _clean(form.get("name", ""))
    email = _clean(form.get("email", ""))
    interest = _clean(form.get("interest", ""))
    phone = _clean(form.get("phone", ""))
    company = _clean(form.get("company", ""))
    message = _clean(form.get("message", ""))

    if not name or not email:
        return HTMLResponse("Missing required fields.", status_code=400)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (name, email, interest, phone, company, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, email, interest, phone, company, message, now_iso()))
    conn.commit()
    conn.close()

    return RedirectResponse("/lead/thanks", status_code=303)

@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return templates.TemplateResponse("lead_thanks.html", {"request": request, "year": datetime.utcnow().year})

# --------------------
# Partner Intake
# --------------------
@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/partner")
async def partner_submit(request: Request):
    form = await request.form()
    name = _clean(form.get("name", ""))
    email = _clean(form.get("email", ""))
    company = _clean(form.get("company", ""))
    role = _clean(form.get("role", ""))
    product_type = _clean(form.get("product_type", ""))
    website = _clean(form.get("website", ""))
    regions = _clean(form.get("regions", ""))
    message = _clean(form.get("message", ""))

    if not name or not email:
        return HTMLResponse("Missing required fields.", status_code=400)

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

# --------------------
# Sponsor Lane
# --------------------
@app.get("/sponsor", response_class=HTMLResponse)
def sponsor_page(request: Request):
    return templates.TemplateResponse("sponsor.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/sponsor/checkout")
def sponsor_checkout(ref: str | None = None):
    # optional sponsor checkout; uses STRIPE_SPONSOR_PRICE_ID if set
    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Missing STRIPE_SECRET_KEY"}, status_code=500)
    if not STRIPE_SPONSOR_PRICE_ID:
        return JSONResponse({"error": "Missing STRIPE_SPONSOR_PRICE_ID"}, status_code=500)
    if STARTUP_URL_ERROR:
        return JSONResponse({"error": STARTUP_URL_ERROR}, status_code=500)
    if not SUCCESS_URL or not CANCEL_URL:
        return JSONResponse({"error": "Missing SUCCESS_URL/CANCEL_URL"}, status_code=500)

    meta = {}
    if ref:
        meta["ref"] = _clean(ref)

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_SPONSOR_PRICE_ID, "quantity": 1}],
        success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=CANCEL_URL,
        metadata=meta,
    )
    return RedirectResponse(session.url, status_code=303)

# --------------------
# Subscriber Legal Intake (protected)
# --------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse(
        "intake_form.html",
        {"request": request, "email": email, "token": token, "year": datetime.utcnow().year}
    )

@app.post("/intake")
async def submit_intake(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err

    form = await request.form()
    name = _clean(form.get("name", ""))
    user_email = _clean(form.get("email", ""))
    service_requested = _clean(form.get("service_requested", ""))
    notes = _clean(form.get("notes", ""))

    if not (name and user_email and service_requested):
        return HTMLResponse("Missing required fields.", status_code=400)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (name, user_email, service_requested, notes, now_iso()))
    conn.commit()
    conn.close()

    # notify admin mailbox (optional)
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber (magic link email): {email}\n\nName: {name}\nEmail: {user_email}\nService: {service_requested}\nNotes: {notes}"
        )

    return JSONResponse({"status": "Intake stored successfully"})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email, "token": token, "year": datetime.utcnow().year})

# --------------------
# Stripe Checkout (public subscriber)
# --------------------
def require_env():
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
    err = require_env()
    if err:
        return err

    meta = {}
    if ref:
        meta["ref"] = _clean(ref)

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=CANCEL_URL,
        metadata=meta,
    )
    return RedirectResponse(session.url, status_code=303)

@app.get("/success", response_class=HTMLResponse)
def success(request: Request, session_id: str | None = None):
    token = None
    email = None
    dashboard_link = None

    if session_id and STRIPE_SECRET_KEY:
        try:
            s = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])
            if s and s.get("status") in ("complete", "completed"):
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

# --------------------
# Stripe Webhook
# --------------------
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

# --------------------
# AVPT / LMT Intakes + Results
# --------------------
@app.get("/intake/production", response_class=HTMLResponse)
def intake_production(request: Request):
    return templates.TemplateResponse("intake_production.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor(request: Request):
    return templates.TemplateResponse("intake_labor.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/intake/production")
async def submit_production(request: Request):
    form = await request.form()
    payload = {k: _clean(form.get(k, "")) for k in form.keys()}

    flags = risk_flags_production(payload)
    routed = route_lane_by_flags(flags)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO avpt_jobs (
        company_name, contact_name, contact_email, contact_phone,
        city, state, venue, show_type, load_in_date, load_out_date, call_time,
        headcount_needed, roles_needed,
        truck_size, liftgate, power_notes, union_terms,
        budget_notes, additional_notes,
        risk_flags, routed_to, created_at
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.get("company_name",""),
        payload.get("contact_name",""),
        payload.get("contact_email",""),
        payload.get("contact_phone",""),
        payload.get("city",""),
        payload.get("state",""),
        payload.get("venue",""),
        payload.get("show_type",""),
        payload.get("load_in_date",""),
        payload.get("load_out_date",""),
        payload.get("call_time",""),
        int(payload.get("headcount_needed") or 0),
        payload.get("roles_needed",""),
        payload.get("truck_size",""),
        payload.get("liftgate",""),
        payload.get("power_notes",""),
        payload.get("union_terms",""),
        payload.get("budget_notes",""),
        payload.get("additional_notes",""),
        JSONResponse(content=flags).body.decode("utf-8"),
        routed,
        now_iso(),
    ))
    job_id = cur.lastrowid
    conn.commit()
    conn.close()

    # route to results page
    return RedirectResponse(f"/results?lane=production&id={job_id}", status_code=303)

@app.post("/intake/labor")
async def submit_labor(request: Request):
    form = await request.form()
    payload = {k: _clean(form.get(k, "")) for k in form.keys()}

    flags = risk_flags_labor(payload)
    routed = route_lane_by_flags(flags)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO lmt_workers (
        name, email, phone, city, state,
        primary_role, skills, certs,
        has_llc, has_insurance,
        travel_ok, transportation, availability,
        union_member, pay_expectation, notes,
        risk_flags, routed_to, created_at
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.get("name",""),
        payload.get("email",""),
        payload.get("phone",""),
        payload.get("city",""),
        payload.get("state",""),
        payload.get("primary_role",""),
        payload.get("skills",""),
        payload.get("certs",""),
        payload.get("has_llc",""),
        payload.get("has_insurance",""),
        payload.get("travel_ok",""),
        payload.get("transportation",""),
        payload.get("availability",""),
        payload.get("union_member",""),
        payload.get("pay_expectation",""),
        payload.get("notes",""),
        JSONResponse(content=flags).body.decode("utf-8"),
        routed,
        now_iso(),
    ))
    worker_id = cur.lastrowid
    conn.commit()
    conn.close()

    return RedirectResponse(f"/results?lane=labor&id={worker_id}", status_code=303)

@app.get("/results", response_class=HTMLResponse)
def results(request: Request, lane: str, id: int):
    lane = _clean(lane).lower()
    conn = db()
    cur = conn.cursor()

    record = None
    flags = []
    routed = ""

    if lane == "production":
        cur.execute("SELECT * FROM avpt_jobs WHERE id = ? LIMIT 1", (id,))
        row = cur.fetchone()
        if row:
            record = dict(row)
            routed = record.get("routed_to","")
            try:
                flags = JSONResponse(content={}).json().loads(record.get("risk_flags","[]"))  # placeholder
            except:
                flags = []
            # safe parse
            try:
                import json
                flags = json.loads(record.get("risk_flags","[]") or "[]")
            except:
                flags = []
    elif lane == "labor":
        cur.execute("SELECT * FROM lmt_workers WHERE id = ? LIMIT 1", (id,))
        row = cur.fetchone()
        if row:
            record = dict(row)
            routed = record.get("routed_to","")
            try:
                import json
                flags = json.loads(record.get("risk_flags","[]") or "[]")
            except:
                flags = []
    conn.close()

    if not record:
        return HTMLResponse("Detail not found.", status_code=404)

    # next-step dashboard links
    dash_link = "/dash/production" if lane == "production" else "/dash/labor"

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "lane": lane,
            "record": record,
            "flags": flags,
            "routed": routed,
            "dash_link": dash_link,
            "year": datetime.utcnow().year,
        },
    )

# --------------------
# Dashboards (public-facing lane dashboards)
# --------------------
@app.get("/dash/production", response_class=HTMLResponse)
def dash_production(request: Request):
    # lightweight list: last 20 jobs
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id, company_name, city, state, show_type, created_at, routed_to FROM avpt_jobs ORDER BY id DESC LIMIT 20")
    jobs = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("dash_production.html", {"request": request, "jobs": jobs, "year": datetime.utcnow().year})

@app.get("/dash/labor", response_class=HTMLResponse)
def dash_labor(request: Request):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, city, state, primary_role, created_at, routed_to FROM lmt_workers ORDER BY id DESC LIMIT 20")
    workers = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("dash_labor.html", {"request": request, "workers": workers, "year": datetime.utcnow().year})

# --------------------
# Director / Operator Dashboard (links wired)
# --------------------
@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    k = get_admin_k(request)
    admin_ok = False
    if _clean(os.getenv("ADMIN_KEY","")) and k == _clean(os.getenv("ADMIN_KEY","")):
        admin_ok = True

    # buttons render either disabled (no key) or linked with key
    return templates.TemplateResponse(
        "dashboards.html",
        {
            "request": request,
            "k": k,
            "admin_ok": admin_ok,
            "year": datetime.utcnow().year
        }
    )

# --------------------
# Admin Dashboards
# --------------------
@app.get("/admin/leads-dashboard", response_class=HTMLResponse)
def leads_dashboard(request: Request, k: str | None = None, key: str | None = None):
    k = k or key
    require_admin(k)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 200")
    leads = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("admin_leads.html", {"request": request, "leads": leads, "k": k, "year": datetime.utcnow().year})

@app.get("/admin/partners-dashboard", response_class=HTMLResponse)
def partners_dashboard(request: Request, k: str | None = None, key: str | None = None, q: str = "", product: str = "", region: str = ""):
    k = k or key
    require_admin(k)
    conn = db()
    cur = conn.cursor()

    query = "SELECT * FROM partners WHERE 1=1"
    params = []

    if q:
        query += " AND (name LIKE ? OR email LIKE ? OR company LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if product:
        query += " AND product_type LIKE ?"
        params.append(f"%{product}%")
    if region:
        query += " AND regions LIKE ?"
        params.append(f"%{region}%")

    query += " ORDER BY id DESC LIMIT 300"
    cur.execute(query, params)
    partners = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "admin_partners.html",
        {"request": request, "partners": partners, "k": k, "q": q, "product": product, "region": region, "year": datetime.utcnow().year},
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
    k = k or key
    require_admin(k)
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

    query += " ORDER BY score DESC LIMIT 300"

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "contributors_dashboard.html",
        {"request": request, "contributors": rows, "rail": rail, "min_score": min_score, "track": track, "k": k, "year": datetime.utcnow().year},
    )

@app.post("/admin/contributor-status")
async def update_contributor_status(request: Request):
    form = await request.form()
    k = _clean(form.get("k", "")) or _clean(form.get("key",""))
    require_admin(k)

    cid = int(form.get("id", "0") or "0")
    status = _clean(form.get("status", "")) or "new"

    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, cid))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/admin/contributors-dashboard?k={k}", status_code=303)

@app.get("/admin/people-dashboard", response_class=HTMLResponse)
def people_dashboard(request: Request, k: str | None = None, key: str | None = None):
    k = k or key
    require_admin(k)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people ORDER BY role DESC, id ASC")
    people = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "admin_people.html",
        {"request": request, "people": people, "k": k, "year": datetime.utcnow().year},
    )

@app.post("/admin/create-operator")
async def create_operator(request: Request):
    form = await request.form()
    k = _clean(form.get("k","")) or _clean(form.get("key",""))
    require_admin(k)

    name = _clean(form.get("name",""))
    email = _clean(form.get("email","")).lower()

    if not name or "@" not in email:
        return JSONResponse({"error": "Missing/invalid name/email"}, status_code=400)

    ref = make_ref_code("OP")

    # Find (or create) Duece director record if needed
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM people WHERE role='director' AND ref_code LIKE 'DEU%' ORDER BY id ASC LIMIT 1")
    row = cur.fetchone()
    if row:
        duece_id = int(row["id"])
    else:
        duece_ref = "DEUC46E"  # your current known ref
        cur.execute("INSERT INTO people (name, email, role, ref_code, parent_id, created_at) VALUES (?, ?, 'director', ?, NULL, ?)",
                    ("Duece", "duece@local", duece_ref, now_iso()))
        duece_id = cur.lastrowid

    cur.execute("""
        INSERT INTO people (name, email, role, ref_code, parent_id, created_at)
        VALUES (?, ?, 'operator', ?, ?, ?)
    """, (name, email, ref, duece_id, now_iso()))
    conn.commit()
    conn.close()

    base = "https://nautical-compass-9rjs6.ondigitalocean.app"
    return JSONResponse({
        "ok": True,
        "ref_code": ref,
        "operator_link": f"{base}/checkout?ref={ref}"
    })

# --------------------
# Contributor Intake + Admin scoring
# --------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/contributor")
async def submit_contributor(request: Request):
    form = await request.form()
    # build ContributorForm manually (keeps it stable with html forms)
    data = {k: _clean(form.get(k, "")) for k in form.keys()}
    # EmailStr validation is stricter; do a soft check first
    if "@" not in data.get("email",""):
        return HTMLResponse("Invalid email.", status_code=400)

    cf = ContributorForm(**{
        "name": data.get("name",""),
        "email": data.get("email",""),
        "phone": data.get("phone",""),
        "company": data.get("company",""),
        "website": data.get("website",""),
        "primary_role": data.get("primary_role",""),
        "contribution_track": data.get("contribution_track",""),
        "position_interest": data.get("position_interest",""),
        "comp_plan": data.get("comp_plan",""),
        "director_owner": data.get("director_owner","Duece"),
        "assets": data.get("assets",""),
        "regions": data.get("regions",""),
        "capacity": data.get("capacity",""),
        "alignment": data.get("alignment",""),
        "message": data.get("message",""),
        "fit_access": data.get("fit_access",""),
        "fit_build_goal": data.get("fit_build_goal",""),
        "fit_opportunity": data.get("fit_opportunity",""),
        "fit_authority": data.get("fit_authority",""),
        "fit_lane": data.get("fit_lane",""),
        "fit_no_conditions": data.get("fit_no_conditions",""),
        "fit_visibility": data.get("fit_visibility",""),
        "fit_why_you": data.get("fit_why_you",""),
    })

    score = _score_contributor(cf)
    rail = _assign_rail(cf, score)

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
        cf.name, str(cf.email), cf.phone, cf.company, cf.website,
        cf.primary_role,
        cf.contribution_track, cf.position_interest, cf.comp_plan, cf.director_owner,
        cf.assets, cf.regions, cf.capacity, cf.alignment, cf.message,
        cf.fit_access, cf.fit_build_goal, cf.fit_opportunity, cf.fit_authority,
        cf.fit_lane, cf.fit_no_conditions, cf.fit_visibility, cf.fit_why_you,
        score, rail, "new", now_iso()
    ))
    conn.commit()
    conn.close()

    return JSONResponse({"status": "Contributor submission received", "rail_assigned": rail, "score": score})

# --------------------
# Dev Token Route (kept)
# --------------------
DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))

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

# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
