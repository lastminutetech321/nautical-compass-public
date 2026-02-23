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
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr

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
# Helpers: env cleaning + URL validation
# ============================================================
def _clean(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", "").strip()

def _clean_url(s: str) -> str:
    s = _clean(s)
    # Handle accidental "Value:" prefix pasted into env UI
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

# ============================================================
# Stripe Config
# ============================================================
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))  # Public membership price
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

# Sponsor price (optional): your $5k/mo manufacturer access price id
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

# ============================================================
# Email (optional)
# ============================================================
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))

SMTP_HOST = _clean(os.getenv("SMTP_HOST", "")) or "smtp.gmail.com"
SMTP_PORT = int(_clean(os.getenv("SMTP_PORT", "")) or "465")

# ============================================================
# Admin + Dev toggles
# ============================================================
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes", "on")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))

# ============================================================
# The Veil (Dormant Rails)
# ============================================================
VEIL_MODE = _clean(os.getenv("VEIL_MODE", "false")).lower() in ("1", "true", "yes", "on")
VEIL_KEY = _clean(os.getenv("VEIL_KEY", ""))  # optional query gate

# ============================================================
# DB
# ============================================================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# Admin guard
# ============================================================
def require_admin(k: Optional[str]):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY is not set")
    if not k or _clean(k) != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Bad admin key")

# ============================================================
# Referral / People system (Operator + Director)
# ============================================================
DUECE_REF = "DEUC46E"   # locked code for Duece (Owner/Director)
DUECE_ID = 1            # reserved People row id for Duece (we will upsert)

def make_ref_code(prefix: str = "OP") -> str:
    # 6 chars, readable
    return f"{prefix}{secrets.token_hex(3).upper()}"

# ============================================================
# Tables
# ============================================================
def init_db():
    conn = db()
    cur = conn.cursor()

    # Public subscriber intake items
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

    # Public lead capture
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            company TEXT,
            interest TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Manufacturer / sponsor partner lane
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

    # Subscription status
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

    # Contributors (builders/operators/vendors/capital)
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

    # People (Director + Operators)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,              -- 'director' or 'operator'
            ref_code TEXT UNIQUE NOT NULL,   -- e.g. DEUC46E, OPXXXXXX
            parent_id INTEGER,               -- director id for operators
            created_at TEXT NOT NULL
        )
    """)

    # Referrals (tracking the ref param we get on checkout)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_code TEXT NOT NULL,
            email TEXT,
            stripe_session_id TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Sponsor leads from sponsor checkout (optional tracking)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sponsors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT,
            contact_email TEXT,
            ref_code TEXT,
            stripe_session_id TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL
        )
    """)

    # The Veil tables (dormant)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS veil_leads (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            email TEXT NOT NULL,
            intent TEXT,
            experience_level TEXT,
            primary_role TEXT,
            track TEXT,
            score_frontend INTEGER DEFAULT 0,
            score_backend INTEGER DEFAULT 0,
            score_data INTEGER DEFAULT 0,
            score_devops INTEGER DEFAULT 0,
            score_security INTEGER DEFAULT 0,
            score_product INTEGER DEFAULT 0,
            tools TEXT,
            availability_hours_per_week INTEGER,
            pain_points TEXT,
            source TEXT,
            utm_source TEXT,
            utm_medium TEXT,
            utm_campaign TEXT,
            referrer TEXT,
            status TEXT NOT NULL DEFAULT 'new'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS veil_submissions (
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            portfolio_links TEXT,
            ecosystem_interest TEXT,
            comm_preference TEXT,
            contribution_type TEXT,
            nda_ack INTEGER DEFAULT 0,
            challenge_choice TEXT,
            challenge_response TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending',
            review_notes TEXT
        )
    """)

    conn.commit()

    # Upsert Duece in people table
    cur.execute("SELECT id FROM people WHERE ref_code = ? LIMIT 1", (DUECE_REF,))
    row = cur.fetchone()
    if not row:
        cur.execute("""
            INSERT INTO people (id, name, email, role, ref_code, parent_id, created_at)
            VALUES (?, ?, ?, 'director', ?, NULL, ?)
        """, (DUECE_ID, "Duece", "duece@example.com", DUECE_REF, now_iso()))
        conn.commit()

    conn.close()

init_db()

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

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)

# ============================================================
# Subscription helpers
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

def require_subscriber_token(token: Optional[str]):
    if not token:
        return None, HTMLResponse("Missing token.", status_code=401)

    email = validate_magic_link(token)
    if not email:
        return None, HTMLResponse("Invalid or expired link.", status_code=401)

    if not is_active_subscriber(email):
        return None, HTMLResponse("Subscription not active.", status_code=403)

    return email, None

# ============================================================
# Models (JSON-only endpoints use these; forms use Form())
# ============================================================
class IntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: str | None = None

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

# ============================================================
# Contributor scoring + rail assignment
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
# Pages
# ============================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.utcnow().year})

# ============================================================
# Lead Intake (PUBLIC) - FIXED to accept FORM (not JSON)
# ============================================================
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
    return {"status": "Lead received"}

# ============================================================
# Partner / Manufacturer Intake (PUBLIC) - FIXED to accept FORM
# ============================================================
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
    return {"status": "Partner submission received"}

# ============================================================
# Subscriber Intake (TOKEN protected)
# ============================================================
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

    return {"status": "Intake stored successfully"}

@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}

# ============================================================
# Stripe Checkout (PUBLIC)
# Supports referral param: ?ref=DEUC46E or ?ref=OPXXXXXX
# ============================================================
def require_stripe_env(public: bool = True):
    if STARTUP_URL_ERROR:
        return JSONResponse({"error": STARTUP_URL_ERROR, "hint": "Fix SUCCESS_URL and CANCEL_URL env vars to valid https:// URLs."}, status_code=500)
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

@app.get("/checkout")
def checkout(ref: Optional[str] = None):
    err = require_stripe_env()
    if err:
        return err

    ref = _clean(ref or "")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
            metadata={"ref_code": ref} if ref else {},
        )

        # Save referral marker (optional)
        if ref:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO referrals (ref_code, email, stripe_session_id, created_at) VALUES (?, ?, ?, ?)",
                (ref, "", session.id, now_iso())
            )
            conn.commit()
            conn.close()

        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================
# Sponsor Checkout (Manufacturer Access)
# ============================================================
@app.get("/sponsor", response_class=HTMLResponse)
def sponsor_page(request: Request):
    return templates.TemplateResponse("sponsor.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/sponsor/checkout")
def sponsor_checkout(ref: Optional[str] = None):
    if STARTUP_URL_ERROR:
        return JSONResponse({"error": STARTUP_URL_ERROR}, status_code=500)
    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Missing STRIPE_SECRET_KEY"}, status_code=500)
    if not STRIPE_SPONSOR_PRICE_ID:
        return JSONResponse({"error": "Missing STRIPE_SPONSOR_PRICE_ID"}, status_code=500)
    if not SUCCESS_URL or not CANCEL_URL:
        return JSONResponse({"error": "Missing SUCCESS_URL or CANCEL_URL"}, status_code=500)

    ref = _clean(ref or "")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_SPONSOR_PRICE_ID, "quantity": 1}],
            success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
            metadata={"ref_code": ref, "lane": "sponsor"} if ref else {"lane": "sponsor"},
        )

        if ref:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sponsors (company, contact_email, ref_code, stripe_session_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("", "", ref, session.id, "new", now_iso())
            )
            conn.commit()
            conn.close()

        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================
# Success + Cancel pages
# Success generates token if session_id is present
# ============================================================
@app.get("/success", response_class=HTMLResponse)
def success(request: Request, session_id: Optional[str] = None):
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
        {"request": request, "token": token, "email": email, "dashboard_link": dashboard_link, "year": datetime.utcnow().year},
    )

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request, "year": datetime.utcnow().year})

# ============================================================
# Stripe Webhook (GRANTS ACCESS)
# IMPORTANT: Stripe endpoint must match this path exactly:
#   /stripe/webhook
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
        ref_code = (session.get("metadata", {}) or {}).get("ref_code", "")

        if customer_email:
            upsert_subscriber_active(customer_email, customer_id, subscription_id)

            token = issue_magic_link(customer_email, hours=24)
            base = str(request.base_url).rstrip("/")
            link = f"{base}/dashboard?token={token}"

            # Update referral row with email if we have one
            if ref_code:
                conn = db()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE referrals
                    SET email = ?
                    WHERE ref_code = ? AND stripe_session_id = ?
                """, (customer_email, ref_code, session.get("id", "")))
                conn.commit()
                conn.close()

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

# Backwards-compatible alias (if any old configs still point here)
@app.post("/webhook/stripe")
async def stripe_webhook_alias(request: Request):
    return await stripe_webhook(request)

# ============================================================
# Dashboard (TOKEN protected)
# ============================================================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "email": email, "token": token, "year": datetime.utcnow().year},
    )

# ============================================================
# Contributor Intake (PUBLIC)
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

    return JSONResponse({"status": "Contributor submission received", "rail_assigned": rail, "score": score})

# ============================================================
# Admin Dashboards (ADMIN_KEY protected)
# ============================================================
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

    query += " ORDER BY score DESC"

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "contributors_dashboard.html",
        {
            "request": request,
            "contributors": rows,
            "rail": rail,
            "min_score": min_score,
            "track": track,
            "k": k,
            "year": datetime.utcnow().year,
        },
    )

@app.post("/admin/contributor-status")
def update_contributor_status(id: int = Form(...), status: str = Form(...), k: Optional[str] = None, key: Optional[str] = None):
    k = k or key
    require_admin(k)

    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/admin/partners-dashboard", response_class=HTMLResponse)
def partners_dashboard(
    request: Request,
    k: Optional[str] = None,
    key: Optional[str] = None,
    q: str = "",
    product: str = "",
    region: str = "",
):
    k = k or key
    require_admin(k)

    conn = db()
    cur = conn.cursor()

    query = "SELECT * FROM partners WHERE 1=1"
    params = []

    if q.strip():
        query += " AND (name LIKE ? OR email LIKE ? OR company LIKE ? OR message LIKE ?)"
        like = f"%{q.strip()}%"
        params.extend([like, like, like, like])

    if product.strip():
        query += " AND product_type LIKE ?"
        params.append(f"%{product.strip()}%")

    if region.strip():
        query += " AND regions LIKE ?"
        params.append(f"%{region.strip()}%")

    query += " ORDER BY id DESC LIMIT 500"

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "partners_dashboard.html",
        {"request": request, "partners": rows, "q": q, "product": product, "region": region, "k": k, "year": datetime.utcnow().year},
    )

@app.get("/admin/people-dashboard", response_class=HTMLResponse)
def people_dashboard(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    k = k or key
    require_admin(k)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people ORDER BY role DESC, id ASC")
    people = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "admin_people.html",
        {"request": request, "people": people, "duece_ref": DUECE_REF, "k": k, "year": datetime.utcnow().year},
    )

@app.post("/admin/create-operator")
def create_operator(payload: CreateOperator, k: Optional[str] = None, key: Optional[str] = None):
    k = k or key
    require_admin(k)

    ref = make_ref_code("OP")

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO people (name, email, role, ref_code, parent_id, created_at)
        VALUES (?, ?, 'operator', ?, ?, ?)
    """, (payload.name, str(payload.email), ref, DUECE_ID, now_iso()))
    conn.commit()
    conn.close()

    base = "https://nautical-compass-9rjs6.ondigitalocean.app"
    return {
        "ok": True,
        "ref_code": ref,
        "operator_link": f"{base}/checkout?ref={ref}",
    }

# ============================================================
# Dev Token Route (for testing without paying)
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
# The Veil (Dormant Rails)
# Hidden routes (not linked). If VEIL_MODE=false -> 404.
# Optional key gate: if VEIL_KEY set, require ?k=<VEIL_KEY>
# ============================================================
def _veil_guard(k: Optional[str]):
    if not VEIL_MODE:
        raise HTTPException(status_code=404, detail="Not Found")
    if VEIL_KEY:
        if _clean(k or "") != VEIL_KEY:
            # keep it bland
            raise HTTPException(status_code=404, detail="Not Found")

def _uuid() -> str:
    return secrets.token_hex(16)

@app.get("/veil", response_class=HTMLResponse)
def veil_home(request: Request, k: Optional[str] = None):
    _veil_guard(k)
    return templates.TemplateResponse("veil.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/arkitech", response_class=HTMLResponse)
def arkitech_alias(request: Request, k: Optional[str] = None):
    _veil_guard(k)
    return templates.TemplateResponse("veil.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/veil/check", response_class=HTMLResponse)
def veil_check(request: Request, k: Optional[str] = None):
    _veil_guard(k)
    return templates.TemplateResponse("veil_check.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/veil/intake/l1")
def veil_intake_l1(
    email: str = Form(...),
    intent: str = Form(""),
    experience_level: str = Form(""),
    k: Optional[str] = None
):
    _veil_guard(k)
    lead_id = _uuid()
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO veil_leads (id, created_at, email, intent, experience_level, status)
        VALUES (?, ?, ?, ?, ?, 'new')
    """, (lead_id, now_iso(), _clean(email).lower(), intent, experience_level))
    conn.commit()
    conn.close()
    return {"ok": True, "lead_id": lead_id}

@app.post("/veil/intake/l2")
def veil_intake_l2(
    lead_id: str = Form(...),
    tools: str = Form(""),
    availability_hours_per_week: str = Form(""),
    pain_points: str = Form(""),
    strength_style: str = Form(""),
    preference: str = Form(""),
    k: Optional[str] = None
):
    _veil_guard(k)

    # Simple scoring (stored as ints)
    score_frontend = 0
    score_backend = 0
    score_data = 0
    score_devops = 0
    score_security = 0
    score_product = 0

    pref = (preference or "").lower()
    pp = (pain_points or "").lower()
    tl = (tools or "").lower()
    ss = (strength_style or "").lower()

    if "visual" in pref or "ux" in pref:
        score_frontend += 2
    if "logic" in pref:
        score_backend += 2
    if "data" in pref:
        score_data += 2
    if "systems" in pref or "deploy" in pp:
        score_devops += 2
    if "security" in pp:
        score_security += 2
    if "product" in pref or "people" in pref:
        score_product += 2

    if "communicator" in ss:
        score_frontend += 1
        score_product += 1
    if "builder" in ss or "debugger" in ss:
        score_backend += 1
    if "sql" in tl:
        score_data += 1
    if "docker" in tl or "ci" in tl:
        score_devops += 1
    if "protector" in ss:
        score_security += 1
    if "organizer" in ss:
        score_product += 1

    scores = {
        "frontend": score_frontend,
        "backend": score_backend,
        "data": score_data,
        "devops": score_devops,
        "security": score_security,
        "product": score_product,
    }
    track = max(scores, key=scores.get)

    # Role mapping (clean)
    primary_role = "Domain"
    if track == "frontend":
        primary_role = "Frontend"
    elif track == "backend":
        primary_role = "Backend"
    elif track == "data":
        primary_role = "DB"
    elif track == "devops":
        primary_role = "Deploy"
    elif track == "security":
        primary_role = "Auth"
    elif track == "product":
        primary_role = "API"

    try:
        hrs = int("".join([c for c in (availability_hours_per_week or "") if c.isdigit()]) or "0")
    except Exception:
        hrs = 0

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE veil_leads
        SET
            tools = ?,
            availability_hours_per_week = ?,
            pain_points = ?,
            track = ?,
            primary_role = ?,
            score_frontend = ?,
            score_backend = ?,
            score_data = ?,
            score_devops = ?,
            score_security = ?,
            score_product = ?,
            status = 'routed'
        WHERE id = ?
    """, (
        tools, hrs, pain_points, track, primary_role,
        score_frontend, score_backend, score_data, score_devops, score_security, score_product,
        lead_id
    ))
    conn.commit()
    conn.close()

    return {"ok": True, "lead_id": lead_id, "track": track, "role": primary_role}

@app.post("/veil/intake/l3")
def veil_intake_l3(
    lead_id: str = Form(...),
    portfolio_links: str = Form(""),
    ecosystem_interest: str = Form(""),
    comm_preference: str = Form(""),
    contribution_type: str = Form(""),
    nda_ack: str = Form(""),
    challenge_choice: str = Form(""),
    challenge_response: str = Form(""),
    k: Optional[str] = None
):
    _veil_guard(k)
    sid = _uuid()
    nda = 1 if (nda_ack or "").lower() in ("1", "true", "yes", "on") else 0

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO veil_submissions (
            id, lead_id, created_at, portfolio_links, ecosystem_interest, comm_preference,
            contribution_type, nda_ack, challenge_choice, challenge_response, review_status, review_notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '')
    """, (
        sid, lead_id, now_iso(), portfolio_links, ecosystem_interest, comm_preference,
        contribution_type, nda, challenge_choice, challenge_response
    ))
    conn.commit()
    conn.close()

    return {"ok": True, "submission_id": sid, "review_status": "pending"}

# ============================================================
# Favicon
# ============================================================
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
