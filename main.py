import os
import sqlite3
import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, List, Dict, Any

import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr

# ============================================================
# Nautical Compass (NC) + AVPT/LMT unified app (clarity-first)
# ============================================================

# --------------------
# Paths
# --------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nc.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# --------------------
# App
# --------------------
app = FastAPI(title="Nautical Compass")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --------------------
# Helpers
# --------------------
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

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --------------------
# Env / Config
# --------------------
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

# Stripe
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

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

# Email (optional)
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))
SMTP_HOST = _clean(os.getenv("SMTP_HOST", "smtp.gmail.com"))
SMTP_PORT = int(_clean(os.getenv("SMTP_PORT", "465")) or 465)

# Dev token route (optional)
DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))

# --------------------
# Admin guard
# --------------------
def require_admin(k: str | None):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY is not set on server.")
    if not k:
        raise HTTPException(status_code=401, detail="Admin key missing. Use ?k=ADMIN_KEY")
    if _clean(k) != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key.")

# --------------------
# Email helper
# --------------------
def send_email(to_email: str, subject: str, body: str):
    if not (EMAIL_USER and EMAIL_PASS):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg.set_content(body)

        # If you use Mailgun, set SMTP_HOST/SMTP_PORT accordingly.
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)

# ============================================================
# DB schema (minimal but complete)
# ============================================================
def init_db():
    conn = db()
    cur = conn.cursor()

    # Public inquiries
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

    # Partners
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

    # Subscribers (NC access)
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

    # Magic links (subscriber access)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS magic_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # NC subscriber intake
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nc_intake (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_email TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            service_requested TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # AVPT Production requests (clients)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS avpt_production_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            website TEXT,
            event_name TEXT,
            venue_name TEXT,
            city TEXT,
            state TEXT,
            load_in_date TEXT,
            show_date TEXT,
            load_out_date TEXT,
            call_time TEXT,
            wrap_time TEXT,
            crew_needed TEXT,
            gear_needed TEXT,
            truck_needed TEXT,
            lift_gate INTEGER DEFAULT 0,
            dock_access INTEGER DEFAULT 0,
            union_required INTEGER DEFAULT 0,
            budget_range TEXT,
            payment_terms TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # LMT Labor profiles (workers)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lmt_labor_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            home_city TEXT,
            home_state TEXT,
            roles TEXT,
            experience_level TEXT,
            certs TEXT,
            has_llc INTEGER DEFAULT 0,
            has_insurance INTEGER DEFAULT 0,
            w9_ready INTEGER DEFAULT 0,
            id_ready INTEGER DEFAULT 0,
            transport_mode TEXT,
            can_travel INTEGER DEFAULT 0,
            availability_next_7 TEXT,
            preferred_rate TEXT,
            last_minute_ok INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Risk flags for any intake (production/labor)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS risk_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,    -- 'production' or 'labor'
            entity_id INTEGER NOT NULL,
            flag_key TEXT NOT NULL,
            title TEXT NOT NULL,
            severity TEXT NOT NULL,       -- 'low'/'med'/'high'
            description TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ============================================================
# Magic link auth (NC subscriber access)
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
        "SELECT email, expires_at FROM magic_links WHERE token_hash=? ORDER BY id DESC LIMIT 1",
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
    cur.execute("SELECT status FROM subscribers WHERE email=? LIMIT 1", (email,))
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
# Risk Flags v1 (simple, powerful)
# ============================================================
def add_flag(entity_type: str, entity_id: int, flag_key: str, title: str, severity: str, description: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO risk_flags (entity_type, entity_id, flag_key, title, severity, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (entity_type, entity_id, flag_key, title, severity, description, now_iso()))
    conn.commit()
    conn.close()

def compute_risk_flags_for_production(row: Dict[str, Any]) -> List[Dict[str, str]]:
    flags = []

    # Payment / terms clarity
    if not (row.get("budget_range") or "").strip():
        flags.append({
            "flag_key": "budget_missing",
            "title": "Budget not specified",
            "severity": "med",
            "description": "No budget range listed. This increases pricing disputes and delays."
        })

    if not (row.get("payment_terms") or "").strip():
        flags.append({
            "flag_key": "payment_terms_missing",
            "title": "Payment terms not specified",
            "severity": "med",
            "description": "No payment terms listed (Net 7/Net 14/Net 30, deposit, same-day, etc.)."
        })

    # Logistics readiness
    if int(row.get("truck_needed") != "" and row.get("truck_needed") is not None) and not row.get("venue_name"):
        flags.append({
            "flag_key": "venue_missing",
            "title": "Venue missing for logistics",
            "severity": "high",
            "description": "Truck/crew logistics require a venue name/address to plan dock/load-in."
        })

    if not row.get("city") or not row.get("state"):
        flags.append({
            "flag_key": "location_incomplete",
            "title": "Location incomplete",
            "severity": "high",
            "description": "City/State missing. This blocks crew matching and travel planning."
        })

    # Crew clarity
    if not (row.get("crew_needed") or "").strip():
        flags.append({
            "flag_key": "crew_roles_missing",
            "title": "Crew roles not specified",
            "severity": "high",
            "description": "Roles missing (A1, A2, V1, LD, PM, Stagehands, Riggers, etc.)."
        })

    return flags

def compute_risk_flags_for_labor(row: Dict[str, Any]) -> List[Dict[str, str]]:
    flags = []

    # Compliance / readiness
    if int(row.get("w9_ready") or 0) != 1:
        flags.append({
            "flag_key": "w9_not_ready",
            "title": "W-9 not ready",
            "severity": "high",
            "description": "W-9 isn’t marked ready. This can delay onboarding and payment."
        })

    if int(row.get("id_ready") or 0) != 1:
        flags.append({
            "flag_key": "id_not_ready",
            "title": "ID not ready",
            "severity": "med",
            "description": "Government ID not marked ready. Some venues/clients require it at check-in."
        })

    if int(row.get("has_insurance") or 0) != 1:
        flags.append({
            "flag_key": "no_insurance",
            "title": "No personal/pro insurance listed",
            "severity": "med",
            "description": "Insurance not listed. VIP lane can help you get covered and increase booking rate."
        })

    # Availability clarity
    if not (row.get("availability_next_7") or "").strip():
        flags.append({
            "flag_key": "availability_missing",
            "title": "Availability not provided",
            "severity": "high",
            "description": "No availability for next 7 days. Matching is weaker without it."
        })

    # Transport
    if not (row.get("transport_mode") or "").strip():
        flags.append({
            "flag_key": "transport_missing",
            "title": "Transportation mode not selected",
            "severity": "low",
            "description": "Transport not selected. Choose car / rideshare / public transit / truck."
        })

    # Roles clarity
    if not (row.get("roles") or "").strip():
        flags.append({
            "flag_key": "roles_missing",
            "title": "Roles not specified",
            "severity": "high",
            "description": "No roles selected. Choose what you can execute under pressure."
        })

    return flags

def list_flags(entity_type: str, entity_id: int) -> List[Dict[str, Any]]:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT flag_key, title, severity, description, created_at
        FROM risk_flags
        WHERE entity_type=? AND entity_id=?
        ORDER BY
          CASE severity WHEN 'high' THEN 1 WHEN 'med' THEN 2 ELSE 3 END,
          id DESC
    """, (entity_type, entity_id))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# ============================================================
# Models (forms)
# ============================================================
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

class NCIntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: Optional[str] = None

class ProductionIntakeForm(BaseModel):
    company_name: str
    contact_name: str
    email: EmailStr
    phone: str = ""
    website: str = ""

    event_name: str = ""
    venue_name: str = ""
    city: str = ""
    state: str = ""
    load_in_date: str = ""
    show_date: str = ""
    load_out_date: str = ""
    call_time: str = ""
    wrap_time: str = ""

    crew_needed: str = ""
    gear_needed: str = ""

    truck_needed: str = ""          # "Sprinter", "Box Truck", "Tractor", etc.
    lift_gate: bool = False
    dock_access: bool = False
    union_required: bool = False

    budget_range: str = ""
    payment_terms: str = ""
    notes: str = ""

class LaborIntakeForm(BaseModel):
    full_name: str
    email: EmailStr
    phone: str = ""
    home_city: str = ""
    home_state: str = ""

    roles: str = ""                 # "A2, V1, Stagehand..."
    experience_level: str = ""      # "Entry / Mid / Senior"
    certs: str = ""                 # "OSHA10, Forklift, Rigging..."
    has_llc: bool = False
    has_insurance: bool = False
    w9_ready: bool = False
    id_ready: bool = False

    transport_mode: str = ""        # "Car / Rideshare / Public Transit / Truck"
    can_travel: bool = False
    availability_next_7: str = ""   # free text or structured later
    preferred_rate: str = ""
    last_minute_ok: bool = False
    notes: str = ""

# ============================================================
# Stripe: require env
# ============================================================
def require_stripe_env():
    if STARTUP_URL_ERROR:
        return JSONResponse({"error": STARTUP_URL_ERROR}, status_code=500)
    missing = []
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

# ============================================================
# Pages (clarity-first)
# ============================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "year": datetime.utcnow().year
    })

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {
        "request": request,
        "year": datetime.utcnow().year
    })

@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request, k: Optional[str] = None):
    # This is the "hall of doors" for internal admin pages.
    admin_ok = bool(ADMIN_KEY) and bool(k) and _clean(k) == ADMIN_KEY
    return templates.TemplateResponse("dashboards.html", {
        "request": request,
        "year": datetime.utcnow().year,
        "admin_ok": admin_ok,
        "k": k or ""
    })

# ============================================================
# Public lead intake
# ============================================================
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
    return RedirectResponse("/lead/thanks", status_code=303)

@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return templates.TemplateResponse("lead_thanks.html", {"request": request, "year": datetime.utcnow().year})

# ============================================================
# Partner intake
# ============================================================
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
    return RedirectResponse("/partner/thanks", status_code=303)

@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return templates.TemplateResponse("partner_thanks.html", {"request": request, "year": datetime.utcnow().year})

# ============================================================
# AVPT — Production Intake (clients)
# ============================================================
@app.get("/intake/production", response_class=HTMLResponse)
def intake_production(request: Request):
    return templates.TemplateResponse("intake_production.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/intake/production")
def submit_production(form: ProductionIntakeForm):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO avpt_production_requests (
            company_name, contact_name, email, phone, website,
            event_name, venue_name, city, state, load_in_date, show_date, load_out_date,
            call_time, wrap_time, crew_needed, gear_needed,
            truck_needed, lift_gate, dock_access, union_required,
            budget_range, payment_terms, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?)
    """, (
        form.company_name, form.contact_name, str(form.email), form.phone, form.website,
        form.event_name, form.venue_name, form.city, form.state, form.load_in_date, form.show_date, form.load_out_date,
        form.call_time, form.wrap_time, form.crew_needed, form.gear_needed,
        form.truck_needed, int(form.lift_gate), int(form.dock_access), int(form.union_required),
        form.budget_range, form.payment_terms, form.notes, now_iso()
    ))
    production_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Risk flags
    row = form.model_dump()
    flags = compute_risk_flags_for_production(row)
    for f in flags:
        add_flag("production", production_id, f["flag_key"], f["title"], f["severity"], f["description"])

    return RedirectResponse(f"/results?type=production&id={production_id}", status_code=303)

# ============================================================
# LMT — Labor Intake (workers)
# ============================================================
@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor(request: Request):
    return templates.TemplateResponse("intake_labor.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/intake/labor")
def submit_labor(form: LaborIntakeForm):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lmt_labor_profiles (
            full_name, email, phone, home_city, home_state,
            roles, experience_level, certs,
            has_llc, has_insurance, w9_ready, id_ready,
            transport_mode, can_travel, availability_next_7,
            preferred_rate, last_minute_ok, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?)
    """, (
        form.full_name, str(form.email), form.phone, form.home_city, form.home_state,
        form.roles, form.experience_level, form.certs,
        int(form.has_llc), int(form.has_insurance), int(form.w9_ready), int(form.id_ready),
        form.transport_mode, int(form.can_travel), form.availability_next_7,
        form.preferred_rate, int(form.last_minute_ok), form.notes, now_iso()
    ))
    labor_id = cur.lastrowid
    conn.commit()
    conn.close()

    flags = compute_risk_flags_for_labor(form.model_dump())
    for f in flags:
        add_flag("labor", labor_id, f["flag_key"], f["title"], f["severity"], f["description"])

    return RedirectResponse(f"/results?type=labor&id={labor_id}", status_code=303)

# ============================================================
# Results page (flags + next steps)
# ============================================================
@app.get("/results", response_class=HTMLResponse)
def results(request: Request, type: str, id: int):
    if type not in ("production", "labor"):
        return HTMLResponse("Invalid results type.", status_code=400)

    flags = list_flags(type, id)

    # pull record for summary
    conn = db()
    cur = conn.cursor()
    if type == "production":
        cur.execute("SELECT * FROM avpt_production_requests WHERE id=?", (id,))
        row = cur.fetchone()
        title = "AVPT Production Request"
    else:
        cur.execute("SELECT * FROM lmt_labor_profiles WHERE id=?", (id,))
        row = cur.fetchone()
        title = "LMT Labor Profile"
    conn.close()

    if not row:
        return HTMLResponse("Not found.", status_code=404)

    return templates.TemplateResponse("results.html", {
        "request": request,
        "year": datetime.utcnow().year,
        "type": type,
        "title": title,
        "record": dict(row),
        "flags": flags
    })

# ============================================================
# Dashboards (public + admin)
# ============================================================
@app.get("/dash/public", response_class=HTMLResponse)
def dash_public(request: Request):
    return templates.TemplateResponse("dash_public.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/dash/production", response_class=HTMLResponse)
def dash_production(request: Request, k: Optional[str] = None):
    # admin view
    if k:
        require_admin(k)
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM avpt_production_requests ORDER BY id DESC LIMIT 200")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return templates.TemplateResponse("dash_production.html", {
            "request": request, "year": datetime.utcnow().year,
            "mode": "admin", "rows": rows, "k": k
        })

    # public explanation view
    return templates.TemplateResponse("dash_production.html", {
        "request": request, "year": datetime.utcnow().year,
        "mode": "public", "rows": [], "k": ""
    })

@app.get("/dash/labor", response_class=HTMLResponse)
def dash_labor(request: Request, k: Optional[str] = None):
    if k:
        require_admin(k)
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM lmt_labor_profiles ORDER BY id DESC LIMIT 300")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return templates.TemplateResponse("dash_labor.html", {
            "request": request, "year": datetime.utcnow().year,
            "mode": "admin", "rows": rows, "k": k
        })
    return templates.TemplateResponse("dash_labor.html", {
        "request": request, "year": datetime.utcnow().year,
        "mode": "public", "rows": [], "k": ""
    })

# ============================================================
# NC subscriber intake (legal) — still token-gated
# ============================================================
@app.get("/intake-form", response_class=HTMLResponse)
def nc_intake_form(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("intake_legal.html", {
        "request": request, "year": datetime.utcnow().year,
        "subscriber_email": email,
        "token": token
    })

@app.post("/intake")
def nc_submit_intake(form: NCIntakeForm, token: str):
    subscriber_email, err = require_subscriber_token(token)
    if err:
        return err

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO nc_intake (subscriber_email, name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (subscriber_email, form.name, form.email, form.service_requested, form.notes or "", now_iso()))
    conn.commit()
    conn.close()

    # optional: notify you
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New NC Subscriber Intake",
            f"Subscriber: {subscriber_email}\nName: {form.name}\nEmail: {form.email}\nService: {form.service_requested}\nNotes: {form.notes}"
        )

    return JSONResponse({"ok": True, "status": "NC intake stored."})

# ============================================================
# Stripe Checkout (NC Access)
# ============================================================
@app.get("/checkout")
def checkout():
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
                            f"Your access link (valid 24 hours):\n{dashboard_link}\n"
                        )
        except Exception as e:
            print("Success page Stripe fetch failed:", e)

    return templates.TemplateResponse("success.html", {
        "request": request, "year": datetime.utcnow().year,
        "token": token, "email": email, "dashboard_link": dashboard_link
    })

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request, "year": datetime.utcnow().year})

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
# Subscriber Dashboard (NC)
# ============================================================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "year": datetime.utcnow().year,
        "email": email, "token": token
    })

# ============================================================
# Dev token route (optional)
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
# Favicon
# ============================================================
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
