import os
import sqlite3
import smtplib
import hashlib
import secrets
from datetime import datetime, timedelta, date
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Any, List, Dict

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

# ============================================================
# Paths (LOCKED)
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nc.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# ============================================================
# App
# ============================================================
app = FastAPI(title="Nautical Compass Intake")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ============================================================
# Helpers / Config
# ============================================================
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
        raise ValueError(f"{name} must start with http:// or https://")
    return url

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def today_iso() -> str:
    return date.today().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def make_ref_code(prefix: str = "NC") -> str:
    token = secrets.token_hex(3).upper()
    return f"{prefix}{token}"

# ============================================================
# Stripe Config
# ============================================================
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))                 # Public $25/mo
STRIPE_SPONSOR_PRICE_ID = _clean(os.getenv("STRIPE_SPONSOR_PRICE_ID", "")) # Sponsor tier (optional)
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

# ============================================================
# Email (optional)
# ============================================================
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))

# ============================================================
# Admin guard (supports both ?k= and ?key=)
# ============================================================
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

def _admin_key_from(k: str | None, key: str | None) -> str | None:
    return _clean(k or key or "")

def require_admin(k: str | None, key: str | None) -> None:
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set")
    provided = _admin_key_from(k, key)
    if not provided or provided != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ============================================================
# Rates (LOCKED)
# ============================================================
OPERATOR_RATE = 0.20
DUECE_DIRECTOR_RATE = 0.30
DUECE_OVERRIDE_RATE = 0.10

PUBLIC_PLAN_MRR_CENTS = int(_clean(os.getenv("PUBLIC_PLAN_MRR_CENTS", "2500")) or "2500")

# ============================================================
# DB
# ============================================================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# Models
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

class IntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: str | None = None

class ContributorForm(BaseModel):
    name: str
    email: str
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
    email: str

# ============================================================
# Tables
# ============================================================
def init_db():
    conn = db()
    cur = conn.cursor()

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
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            product_type TEXT NOT NULL,
            website TEXT,
            regions TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        )
    """)

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

    # People / Ref system (Owner/Director + Operators)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,              -- owner_director | operator
            ref_code TEXT UNIQUE NOT NULL,
            parent_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    # Stripe subscription attribution
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscription_credits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stripe_subscription_id TEXT UNIQUE,
            stripe_customer_id TEXT,
            subscriber_email TEXT,
            plan_code TEXT NOT NULL,          -- public_25 | sponsor
            mrr_cents INTEGER NOT NULL DEFAULT 0,
            credited_person_id INTEGER,
            credited_person_role TEXT,
            status TEXT NOT NULL,             -- active | canceled | incomplete
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # payout ledger (transparent split math)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payout_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            person_id INTEGER NOT NULL,
            person_role TEXT NOT NULL,
            category TEXT NOT NULL,          -- direct | operator_residual | override
            mrr_cents INTEGER NOT NULL,
            payout_cents INTEGER NOT NULL,
            stripe_subscription_id TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ============================================================
# Seed Duece as Owner/Director (LOCKED)
# ============================================================
def ensure_duece_owner():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id, ref_code FROM people WHERE role='owner_director' AND name='Duece' LIMIT 1")
    row = cur.fetchone()
    if row:
        conn.close()
        return int(row["id"]), row["ref_code"]

    ref = make_ref_code("DUE")
    cur.execute(
        "INSERT INTO people (name, email, role, ref_code, parent_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("Duece", "duece@nauticalcompass.local", "owner_director", ref, None, now_iso())
    )
    conn.commit()
    duece_id = cur.lastrowid
    conn.close()
    return int(duece_id), ref

DUECE_ID, DUECE_REF = ensure_duece_owner()

# ============================================================
# Email helper
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
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)

# ============================================================
# Magic Links (subscriber access)
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
    cur.execute("SELECT status FROM subscribers WHERE email=? LIMIT 1", (email,))
    row = cur.fetchone()
    conn.close()
    return bool(row) and row["status"] == "active"

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
# Attribution + ledger (20% operator, 10% Duece override, 30% Duece direct)
# ============================================================
def get_person_by_ref(ref_code: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE ref_code=? LIMIT 1", (_clean(ref_code),))
    row = cur.fetchone()
    conn.close()
    return row

def resolve_credit_target(ref_code: str):
    row = get_person_by_ref(ref_code)
    if row:
        return row
    # fallback to Duece
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE id=? LIMIT 1", (DUECE_ID,))
    duece = cur.fetchone()
    conn.close()
    return duece

def credit_subscription(sub_id: str, customer_id: str, email: str, plan_code: str, mrr_cents: int, person_id: int, role: str, status: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO subscription_credits
        (stripe_subscription_id, stripe_customer_id, subscriber_email, plan_code, mrr_cents, credited_person_id, credited_person_role, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(stripe_subscription_id) DO UPDATE SET
         stripe_customer_id=excluded.stripe_customer_id,
         subscriber_email=excluded.subscriber_email,
         plan_code=excluded.plan_code,
         mrr_cents=excluded.mrr_cents,
         credited_person_id=excluded.credited_person_id,
         credited_person_role=excluded.credited_person_role,
         status=excluded.status,
         updated_at=excluded.updated_at
    """, (sub_id, customer_id, email, plan_code, int(mrr_cents), int(person_id), role, status, now_iso(), now_iso()))
    conn.commit()
    conn.close()

def add_ledger_row(person_id: int, person_role: str, category: str, mrr_cents: int, payout_cents: int, sub_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO payout_ledger (day, person_id, person_role, category, mrr_cents, payout_cents, stripe_subscription_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (today_iso(), person_id, person_role, category, int(mrr_cents), int(payout_cents), sub_id, now_iso()))
    conn.commit()
    conn.close()

def recalc_ledger_for_subscription(sub_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM subscription_credits WHERE stripe_subscription_id=? LIMIT 1", (sub_id,))
    sc = cur.fetchone()
    cur.execute("DELETE FROM payout_ledger WHERE stripe_subscription_id=? AND day=?", (sub_id, today_iso()))
    conn.commit()
    conn.close()

    if not sc or sc["status"] != "active":
        return

    mrr = int(sc["mrr_cents"] or 0)
    credited_id = int(sc["credited_person_id"] or 0)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE id=? LIMIT 1", (credited_id,))
    person = cur.fetchone()
    conn.close()

    if not person:
        return

    if person["role"] == "owner_director":
        payout = int(round(mrr * DUECE_DIRECTOR_RATE))
        add_ledger_row(person["id"], "owner_director", "direct", mrr, payout, sub_id)
        return

    if person["role"] == "operator":
        operator_payout = int(round(mrr * OPERATOR_RATE))
        add_ledger_row(person["id"], "operator", "operator_residual", mrr, operator_payout, sub_id)

        parent_id = int(person["parent_id"] or DUECE_ID)
        override_payout = int(round(mrr * DUECE_OVERRIDE_RATE))
        add_ledger_row(parent_id, "owner_director", "override", mrr, override_payout, sub_id)

# ============================================================
# Env checks
# ============================================================
def require_env_public():
    if STARTUP_URL_ERROR:
        return JSONResponse({"error": STARTUP_URL_ERROR}, status_code=500)
    missing = []
    if not STRIPE_SECRET_KEY: missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_PRICE_ID: missing.append("STRIPE_PRICE_ID")
    if not SUCCESS_URL: missing.append("SUCCESS_URL")
    if not CANCEL_URL: missing.append("CANCEL_URL")
    if missing:
        return JSONResponse({"error":"Missing environment variables","missing":missing}, status_code=500)
    return None

def require_env_sponsor():
    if STARTUP_URL_ERROR:
        return JSONResponse({"error": STARTUP_URL_ERROR}, status_code=500)
    missing = []
    if not STRIPE_SECRET_KEY: missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_SPONSOR_PRICE_ID: missing.append("STRIPE_SPONSOR_PRICE_ID")
    if not SUCCESS_URL: missing.append("SUCCESS_URL")
    if not CANCEL_URL: missing.append("CANCEL_URL")
    if missing:
        return JSONResponse({"error":"Missing environment variables","missing":missing}, status_code=500)
    return None

# ============================================================
# Public Pages
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
    return {"status":"Lead received"}

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
    return {"status":"Partner submission received"}

# ============================================================
# Sponsor (optional)
# ============================================================
@app.get("/sponsor", response_class=HTMLResponse)
def sponsor_page(request: Request):
    return templates.TemplateResponse("sponsor.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/sponsor/checkout")
def sponsor_checkout(ref: str | None = None):
    err = require_env_sponsor()
    if err:
        return err

    ref_code = _clean(ref or "") or DUECE_REF

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_SPONSOR_PRICE_ID, "quantity": 1}],
        success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=CANCEL_URL,
        metadata={"ref_code": ref_code, "plan_code": "sponsor"},
    )
    return RedirectResponse(session.url, status_code=303)

# ============================================================
# Checkout (Public $25/mo)
# ============================================================
@app.get("/checkout")
def checkout(ref: str | None = None):
    err = require_env_public()
    if err:
        return err

    ref_code = _clean(ref or "") or DUECE_REF

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=CANCEL_URL,
        metadata={"ref_code": ref_code, "plan_code": "public_25", "mrr_cents": str(PUBLIC_PLAN_MRR_CENTS)},
    )
    return RedirectResponse(session.url, status_code=303)

# ============================================================
# Success / Cancel
# ============================================================
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
                email = (details.get("email") or "").strip()
                customer_id = str(s.get("customer") or "")
                subscription_id = str(s.get("subscription") or "")

                if email:
                    upsert_subscriber_active(email, customer_id, subscription_id)
                    token = issue_magic_link(email, hours=24)
                    base = str(request.base_url).rstrip("/")
                    dashboard_link = f"{base}/dashboard?token={token}"

                    if EMAIL_USER and EMAIL_PASS:
                        send_email(email, "Your Nautical Compass Access Link", f"Access link (24 hours):\n{dashboard_link}\n")
        except Exception as e:
            print("Success page Stripe fetch failed:", e)

    return templates.TemplateResponse("success.html", {"request": request, "token": token, "email": email, "dashboard_link": dashboard_link, "year": datetime.utcnow().year})

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request, "year": datetime.utcnow().year})

# ============================================================
# Subscriber Intake
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
        send_email(EMAIL_USER, "New Subscriber Intake Submission", f"Subscriber: {email}\nName: {form.name}\nEmail: {form.email}\nService: {form.service_requested}\nNotes: {form.notes}")

    return {"status":"Intake stored successfully"}

# ============================================================
# Dashboard (subscriber-facing)
# ============================================================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email, "token": token, "year": datetime.utcnow().year})

# ============================================================
# Contributors
# ============================================================
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/contributor")
def submit_contributor(form: ContributorForm):
    score = 0
    if form.assets and len(form.assets.strip()) > 10:
        score += 10
    if form.website and len(form.website.strip()) > 6:
        score += 6
    rail = "triage"
    if score >= 25:
        rail = "priority"
    elif score >= 15:
        rail = "review"

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contributors (
            name, email, phone, company, website,
            primary_role, contribution_track, position_interest, comp_plan, director_owner,
            assets, regions, capacity, alignment, message,
            fit_access, fit_build_goal, fit_opportunity, fit_authority,
            fit_lane, fit_no_conditions, fit_visibility, fit_why_you,
            score, rail, status, created_at
        )
        VALUES (?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?)
    """, (
        form.name, form.email, form.phone, form.company, form.website,
        form.primary_role, form.contribution_track, form.position_interest, form.comp_plan, form.director_owner,
        form.assets, form.regions, form.capacity, form.alignment, form.message,
        form.fit_access, form.fit_build_goal, form.fit_opportunity, form.fit_authority,
        form.fit_lane, form.fit_no_conditions, form.fit_visibility, form.fit_why_you,
        score, rail, "new", now_iso()
    ))
    conn.commit()
    conn.close()

    return JSONResponse({"status":"Contributor submission received","rail_assigned":rail,"score":score})

# ============================================================
# ADMIN: Contributors dashboard
# ============================================================
@app.get("/admin/contributors-dashboard", response_class=HTMLResponse)
def contributors_dashboard(request: Request, k: str | None = None, key: str | None = None, rail: Optional[str] = None, min_score: Optional[int] = None, track: Optional[str] = None):
    require_admin(k, key)

    conn = db()
    cur = conn.cursor()
    query = "SELECT * FROM contributors WHERE 1=1"
    params: List[Any] = []

    if rail:
        query += " AND rail=?"
        params.append(rail)
    if min_score is not None:
        query += " AND score >= ?"
        params.append(min_score)
    if track:
        query += " AND contribution_track=?"
        params.append(track)

    query += " ORDER BY score DESC"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse("contributors_dashboard.html", {
        "request": request,
        "contributors": rows,
        "rail": rail,
        "min_score": min_score,
        "track": track,
        "k": _admin_key_from(k, key),
        "year": datetime.utcnow().year
    })

# ============================================================
# ADMIN: Partners dashboard
# ============================================================
@app.get("/admin/partners-dashboard", response_class=HTMLResponse)
def partners_dashboard(request: Request, k: str | None = None, key: str | None = None, q: str = "", product: str = "", region: str = ""):
    require_admin(k, key)

    conn = db()
    cur = conn.cursor()
    query = "SELECT * FROM partners WHERE 1=1"
    params: List[Any] = []

    if q.strip():
        like = f"%{q.strip()}%"
        query += " AND (name LIKE ? OR email LIKE ? OR company LIKE ? OR message LIKE ?)"
        params.extend([like, like, like, like])
    if product.strip():
        query += " AND product_type LIKE ?"
        params.append(f"%{product.strip()}%")
    if region.strip():
        query += " AND regions LIKE ?"
        params.append(f"%{region.strip()}%")

    query += " ORDER BY id DESC"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse("partners_dashboard.html", {
        "request": request,
        "partners": rows,
        "q": q,
        "product": product,
        "region": region,
        "k": _admin_key_from(k, key),
        "year": datetime.utcnow().year
    })

# ============================================================
# ✅ ADMIN: People dashboard (THIS IS WHAT YOU ARE MISSING)
# ============================================================
@app.get("/admin/people-dashboard", response_class=HTMLResponse)
def people_dashboard(request: Request, k: str | None = None, key: str | None = None):
    require_admin(k, key)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people ORDER BY role DESC, id ASC")
    people = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse("admin_people.html", {
        "request": request,
        "people": people,
        "duece_ref": DUECE_REF,
        "k": _admin_key_from(k, key),
        "year": datetime.utcnow().year
    })

@app.post("/admin/create-operator")
def create_operator(payload: CreateOperator, k: str | None = None, key: str | None = None):
    require_admin(k, key)

    name = _clean(payload.name)
    email = _clean(payload.email).lower()

    if not name:
        return JSONResponse({"error": "Name required"}, status_code=400)
    if "@" not in email:
        return JSONResponse({"error": "Valid email required"}, status_code=400)

    ref = make_ref_code("OP")

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO people (name, email, role, ref_code, parent_id, created_at)
        VALUES (?, ?, 'operator', ?, ?, ?)
    """, (name, email, ref, DUECE_ID, now_iso()))
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "ref_code": ref,
        "operator_link": f"https://nautical-compass-9rjs6.ondigitalocean.app/checkout?ref={ref}"
    }

# ============================================================
# Stripe webhook (credit + ledger)
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

    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}

    if etype == "checkout.session.completed":
        session = obj
        customer_id = str(session.get("customer") or "")
        subscription_id = str(session.get("subscription") or "")
        details = session.get("customer_details") or {}
        subscriber_email = (details.get("email") or "").strip()

        meta = session.get("metadata") or {}
        ref_code = _clean(meta.get("ref_code", "")) or DUECE_REF
        plan_code = _clean(meta.get("plan_code", "")) or "public_25"

        mrr_cents = PUBLIC_PLAN_MRR_CENTS
        if _clean(str(meta.get("mrr_cents", ""))).isdigit():
            mrr_cents = int(_clean(str(meta.get("mrr_cents"))))

        target = resolve_credit_target(ref_code)
        credited_person_id = int(target["id"])
        credited_role = target["role"]

        if subscriber_email:
            upsert_subscriber_active(subscriber_email, customer_id, subscription_id)

        credit_subscription(subscription_id, customer_id, subscriber_email, plan_code, mrr_cents, credited_person_id, credited_role, "active")
        recalc_ledger_for_subscription(subscription_id)

    if etype == "customer.subscription.deleted":
        sub = obj
        subscription_id = str(sub.get("id") or "")
        conn = db()
        cur = conn.cursor()
        cur.execute("UPDATE subscription_credits SET status='canceled', updated_at=? WHERE stripe_subscription_id=?", (now_iso(), subscription_id))
        cur.execute("DELETE FROM payout_ledger WHERE stripe_subscription_id=? AND day=?", (subscription_id, today_iso()))
        conn.commit()
        conn.close()

    return {"received": True}

# Alias (if Stripe endpoint is set here)
@app.post("/webhook/stripe")
async def stripe_webhook_alias(request: Request):
    return await stripe_webhook(request)

# ============================================================
# Favicon
# ============================================================
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
