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
# Helpers: env cleaning
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

# --------------------
# Stripe Config
# --------------------
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

# Sponsor lane (optional)
SPONSOR_PRICE_ID = _clean(os.getenv("SPONSOR_PRICE_ID", ""))

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
# Email (Option 1 backup)
# --------------------
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))

# Preferred: Mailgun / custom SMTP (if set)
SMTP_HOST = _clean(os.getenv("SMTP_HOST", ""))         # e.g. smtp.mailgun.org
SMTP_PORT = _clean(os.getenv("SMTP_PORT", ""))         # e.g. 587
SMTP_LOGIN = _clean(os.getenv("SMTP_LOGIN", ""))       # e.g. postmaster@...
SMTP_PASSWORD = _clean(os.getenv("SMTP_PASSWORD", "")) # SMTP password

def send_email(to_email: str, subject: str, body: str):
    """
    Option 1 backup: emails every submission.
    Works with Mailgun SMTP if SMTP_* vars are set.
    Falls back to Gmail SMTP if EMAIL_USER/EMAIL_PASS are set.
    If nothing is set, silently does nothing.
    """
    if not to_email:
        return

    # Prefer custom SMTP (Mailgun)
    if SMTP_HOST and SMTP_PORT and SMTP_LOGIN and SMTP_PASSWORD:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = SMTP_LOGIN
            msg["To"] = to_email
            msg.set_content(body)

            port_int = int(SMTP_PORT)
            with smtplib.SMTP(SMTP_HOST, port_int) as smtp:
                smtp.starttls()
                smtp.login(SMTP_LOGIN, SMTP_PASSWORD)
                smtp.send_message(msg)
            return
        except Exception as e:
            print("SMTP (custom) email failed:", e)
            # fall through to gmail if available

    # Fallback: Gmail SMTP
    if EMAIL_USER and EMAIL_PASS:
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
            print("SMTP (gmail) email failed:", e)

def backup_notify(subject: str, body: str):
    """
    Sends admin backup copy to you.
    If EMAIL_USER isn't set, does nothing.
    """
    if EMAIL_USER:
        send_email(EMAIL_USER, subject, body)

# --------------------
# DB
# --------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso():
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# --------------------
# Tables
# --------------------
def init_db():
    conn = db()
    cur = conn.cursor()

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
            interest TEXT NOT NULL,
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

    # People table (Duece + operators)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            ref_code TEXT UNIQUE,
            parent_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()

# --------------------
# Admin guard
# --------------------
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

def require_admin(k: str | None, key: str | None = None):
    supplied = _clean(k or "") or _clean(key or "")
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set")
    if supplied != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

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
# Models
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
# Env requirements for Stripe
# --------------------
def require_env():
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

# --------------------
# Public pages
# --------------------
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

    # Option 1 backup (admin email)
    backup_notify(
        "NC Lead Submission",
        f"Name: {form.name}\nEmail: {form.email}\nPhone: {form.phone}\nCompany: {form.company}\nInterest: {form.interest}\nMessage: {form.message}\nTime: {now_iso()}"
    )

    return {"status": "Lead received"}

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

    # Option 1 backup
    backup_notify(
        "NC Partner Submission",
        f"Name: {form.name}\nEmail: {form.email}\nCompany: {form.company}\nRole: {form.role}\nProduct: {form.product_type}\nWebsite: {form.website}\nRegions: {form.regions}\nMessage: {form.message}\nTime: {now_iso()}"
    )

    return {"status": "Partner submission received"}

# --------------------
# Sponsor page + sponsor checkout
# --------------------
@app.get("/sponsor", response_class=HTMLResponse)
def sponsor_page(request: Request):
    return templates.TemplateResponse("sponsor.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/sponsor/checkout")
def sponsor_checkout(ref: str | None = None):
    err = require_env()
    if err:
        return err
    if not SPONSOR_PRICE_ID:
        return JSONResponse({"error": "Missing SPONSOR_PRICE_ID"}, status_code=500)

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": SPONSOR_PRICE_ID, "quantity": 1}],
            success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
            metadata={"ref": ref or ""},
        )
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# --------------------
# Subscriber intake (token protected)
# --------------------
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

    # Option 1 backup
    backup_notify(
        "NC Subscriber Intake Submission",
        f"Subscriber: {email}\n\nName: {form.name}\nEmail: {form.email}\nService: {form.service_requested}\nNotes: {form.notes}\nTime: {now_iso()}"
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

# --------------------
# Checkout (subscriber)
# --------------------
@app.get("/checkout")
def checkout(ref: str | None = None):
    err = require_env()
    if err:
        return err

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
            metadata={"ref": ref or ""},
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

                    # also email access link if email configured
                    if EMAIL_USER or (SMTP_HOST and SMTP_LOGIN):
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

            # Email if configured
            if EMAIL_USER or (SMTP_HOST and SMTP_LOGIN):
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
# Dashboard (token protected)
# --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email, "token": token, "year": datetime.utcnow().year})

# --------------------
# Contributor Intake + Admin
# --------------------
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

    # Option 1 backup
    backup_notify(
        "NC Contributor Submission",
        f"Name: {form.name}\nEmail: {form.email}\nPhone: {form.phone}\nCompany: {form.company}\nWebsite: {form.website}\n"
        f"Primary Role: {form.primary_role}\nTrack: {form.contribution_track}\nPosition Interest: {form.position_interest}\nComp Plan: {form.comp_plan}\nDirector Owner: {form.director_owner}\n"
        f"Assets: {form.assets}\nRegions: {form.regions}\nCapacity: {form.capacity}\nAlignment: {form.alignment}\nMessage: {form.message}\n"
        f"Fit Lane: {form.fit_lane}\nFit Authority: {form.fit_authority}\n"
        f"Score: {score}\nRail: {rail}\nTime: {now_iso()}"
    )

    return JSONResponse({"status": "Contributor submission received", "rail_assigned": rail, "score": score})

@app.get("/admin/contributors-dashboard", response_class=HTMLResponse)
def contributors_dashboard(
    request: Request,
    k: Optional[str] = None,
    key: Optional[str] = None,
    rail: Optional[str] = None,
    min_score: Optional[int] = None,
    track: Optional[str] = None,
):
    require_admin(k, key)

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
        {"request": request, "contributors": rows, "rail": rail, "min_score": min_score, "track": track, "year": datetime.utcnow().year},
    )

@app.post("/admin/contributor-status")
def update_contributor_status(id: int, status: str, k: Optional[str] = None, key: Optional[str] = None):
    require_admin(k, key)
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, id))
    conn.commit()
    conn.close()
    return {"ok": True}

# --------------------
# Partners dashboard (admin)
# --------------------
@app.get("/admin/partners-dashboard", response_class=HTMLResponse)
def partners_dashboard(
    request: Request,
    k: Optional[str] = None,
    key: Optional[str] = None,
    q: str = "",
    product: str = "",
    region: str = "",
):
    require_admin(k, key)

    conn = db()
    cur = conn.cursor()

    query = "SELECT * FROM partners WHERE 1=1"
    params = []

    if q:
        query += " AND (name LIKE ? OR email LIKE ? OR company LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if product:
        query += " AND product_type LIKE ?"
        params.append(f"%{product}%")

    if region:
        query += " AND regions LIKE ?"
        params.append(f"%{region}%")

    query += " ORDER BY id DESC"

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "partners_dashboard.html",
        {"request": request, "partners": rows, "q": q, "product": product, "region": region, "year": datetime.utcnow().year},
    )

# --------------------
# People dashboard + operator creation
# --------------------
DUECE_REF = "DEUC46E"
DUECE_ID = 1

def make_ref_code(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(3).upper()}"

@app.get("/admin/people-dashboard", response_class=HTMLResponse)
def people_dashboard(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    require_admin(k, key)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people ORDER BY role DESC, id ASC")
    people = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "admin_people.html",
        {"request": request, "people": people, "duece_ref": DUECE_REF, "k": (k or key or ""), "year": datetime.utcnow().year},
    )

class CreateOperator(BaseModel):
    name: str
    email: EmailStr

@app.post("/admin/create-operator")
def create_operator(payload: CreateOperator, k: Optional[str] = None, key: Optional[str] = None):
    require_admin(k, key)

    ref = make_ref_code("OP")

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO people (name, email, role, ref_code, parent_id, created_at)
        VALUES (?, ?, 'operator', ?, ?, ?)
    """, (payload.name, str(payload.email), ref, DUECE_ID, now_iso()))
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "ref_code": ref,
        "operator_link": f"https://nautical-compass-9rjs6.ondigitalocean.app/checkout?ref={ref}"
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
