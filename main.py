import os
import sqlite3
import smtplib
import hashlib
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import (
    HTMLResponse,
    FileResponse,
    RedirectResponse,
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel


# =========================
# Paths (LOCKED)
# =========================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nc.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


# =========================
# App
# =========================
app = FastAPI(title="Nautical Compass Intake")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =========================
# Env helpers
# =========================
def _clean(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", "").strip()


def _as_bool(v: str) -> bool:
    return _clean(v).lower() in ("1", "true", "yes", "on")


def _clean_url(s: str) -> str:
    s = _clean(s)
    # in case someone pasted "Value: https://..."
    if s.lower().startswith("value:"):
        s = s.split(":", 1)[1].strip()
    return s


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# =========================
# Stripe Config
# =========================
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

SUCCESS_URL = _clean_url(os.getenv("SUCCESS_URL", ""))
CANCEL_URL = _clean_url(os.getenv("CANCEL_URL", ""))

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


# Sponsor (optional separate price)
SPONSOR_PRICE_ID = _clean(os.getenv("SPONSOR_PRICE_ID", ""))


# =========================
# Email (optional)
# =========================
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))


def send_email(to_email: str, subject: str, body: str):
    # safe no-op until fully configured
    if not (EMAIL_USER and EMAIL_PASS):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg.set_content(body)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)


# =========================
# Admin Key (one key used everywhere)
# =========================
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

def require_admin(k: Optional[str]):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set")
    if not k or _clean(k) != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized (bad admin key)")


# =========================
# Dev Token (for testing without paying)
# =========================
DEV_TOKEN_ENABLED = _as_bool(os.getenv("DEV_TOKEN_ENABLED", "false"))
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))


# =========================
# Duece / People system constants
# =========================
DUECE_REF = _clean(os.getenv("DUECE_REF", "DEUC46E"))  # safe default
DUECE_ID = 1  # internal DB id for the "owner/director" row


# =========================
# Tech / TAK / Halo / Reticulum (Dormant Rails)
# =========================
RETICULUM_ENABLED = _as_bool(os.getenv("RETICULUM_ENABLED", "false"))
TAK_ENABLED = _as_bool(os.getenv("TAK_ENABLED", "false"))
HALO_ENABLED = _as_bool(os.getenv("HALO_ENABLED", "false"))

# If later you want to actually transmit messages externally, you will add:
# RETICULUM_ENDPOINT, TAK_API_KEY, HALO_API_KEY, etc.
# For now: database + outbox + admin view = no cost, no breakage.


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

    # --- core tables ---
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

    # --- People / Operators (Duece + staff rails) ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,            -- 'owner_director', 'operator', 'staff', etc.
            ref_code TEXT NOT NULL,        -- used for /checkout?ref=...
            parent_id INTEGER,             -- Duece is parent
            created_at TEXT NOT NULL
        )
    """)

    # Ensure Duece exists as ID=1 (owner/director)
    cur.execute("SELECT id FROM people WHERE id = ?", (DUECE_ID,))
    row = cur.fetchone()
    if not row:
        cur.execute("""
            INSERT INTO people (id, name, email, role, ref_code, parent_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            DUECE_ID,
            "Duece",
            "duece@nauticalcompass.legal",
            "owner_director",
            DUECE_REF,
            None,
            now_iso(),
        ))

    # --- Comms / Tech rails (Dormant) ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comm_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_email TEXT NOT NULL,
            device_type TEXT NOT NULL,     -- 'tak', 'halo', 'reticulum', 'sms', etc.
            device_id TEXT,                -- identifier / serial / node id
            public_key TEXT,               -- optional later
            meta TEXT,                     -- JSON-ish string
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS message_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_email TEXT,
            to_phone TEXT,
            channel TEXT NOT NULL,         -- 'app', 'sms', 'reticulum', 'tak', 'halo'
            subject TEXT,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',   -- queued/sent/failed
            error TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# Magic links
# =========================
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


def is_active_subscriber(email: str) -> bool:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM subscribers WHERE email = ? LIMIT 1", (email,))
    row = cur.fetchone()
    conn.close()
    return bool(row) and row["status"] == "active"


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
# Models
# =========================
class IntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: Optional[str] = None


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
    email: str  # keep as plain str (avoids email-validator dependency)
    phone: str = ""
    company: str = ""
    website: str = ""

    primary_role: str
    contribution_track: str
    position_interest: str = ""
    comp_plan: str = ""

    # requested spelling
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
    email: str


# =========================
# Contributor scoring + rail assignment
# =========================
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


# =========================
# Env sanity for Stripe
# =========================
def require_env():
    missing = []
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_PRICE_ID:
        missing.append("STRIPE_PRICE_ID")
    if not SUCCESS_URL or not (SUCCESS_URL.startswith("http://") or SUCCESS_URL.startswith("https://")):
        missing.append("SUCCESS_URL")
    if not CANCEL_URL or not (CANCEL_URL.startswith("http://") or CANCEL_URL.startswith("https://")):
        missing.append("CANCEL_URL")
    if missing:
        return JSONResponse({"error": "Missing/invalid environment variables", "missing": missing}, status_code=500)
    return None


# =========================
# Public Pages
# =========================
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
async def lead_submit(request: Request):
    # Accept BOTH JSON and HTML form posts
    ct = (request.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        payload = await request.json()
        form = LeadForm(**payload)
    else:
        data = await request.form()
        form = LeadForm(
            name=str(data.get("name", "")),
            email=str(data.get("email", "")),
            interest=str(data.get("interest", "")),
            phone=str(data.get("phone", "")),
            company=str(data.get("company", "")),
            message=str(data.get("message", "")),
        )

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


@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/partner")
async def partner_submit(request: Request):
    ct = (request.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        payload = await request.json()
        form = PartnerForm(**payload)
    else:
        data = await request.form()
        form = PartnerForm(
            name=str(data.get("name", "")),
            email=str(data.get("email", "")),
            company=str(data.get("company", "")),
            role=str(data.get("role", "")),
            product_type=str(data.get("product_type", "")),
            website=str(data.get("website", "")),
            regions=str(data.get("regions", "")),
            message=str(data.get("message", "")),
        )

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


# =========================
# Subscriber Intake
# =========================
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
async def submit_intake(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err

    ct = (request.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        payload = await request.json()
        form = IntakeForm(**payload)
    else:
        data = await request.form()
        form = IntakeForm(
            name=str(data.get("name", "")),
            email=str(data.get("email", "")),
            service_requested=str(data.get("service_requested", "")),
            notes=str(data.get("notes", "")) or None,
        )

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (form.name, form.email, form.service_requested, form.notes or "", now_iso()))
    conn.commit()
    conn.close()

    # Optional internal notification
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber: {email}\n\nName: {form.name}\nEmail: {form.email}\nService: {form.service_requested}\nNotes: {form.notes}"
        )

    return JSONResponse({"ok": True, "status": "Intake stored successfully"})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email, "token": token, "year": datetime.utcnow().year})


# =========================
# Admin: Intake JSON
# =========================
@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}


# =========================
# Admin: Leads dashboard
# =========================
@app.get("/admin/leads-dashboard", response
