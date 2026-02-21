# main.py  (FULL COMPLETED — adds Contributor table + model + routes + DEV token route)
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
from pydantic import BaseModel, ValidationError

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
# Stripe Config
# --------------------
STRIPE_SECRET_KEY = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
STRIPE_PRICE_ID = (os.getenv("STRIPE_PRICE_ID") or "").strip()
SUCCESS_URL = (os.getenv("SUCCESS_URL") or "").strip()
CANCEL_URL = (os.getenv("CANCEL_URL") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()

# Stop newline/header issues forever
STRIPE_SECRET_KEY = STRIPE_SECRET_KEY.replace("\n", "").replace("\r", "")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# --------------------
# Email (optional)
# --------------------
EMAIL_USER = (os.getenv("EMAIL_USER") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").strip()

# --------------------
# DEV toggle (token generator)
# --------------------
DEV_TOKEN_ENABLED = (os.getenv("DEV_TOKEN_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")

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
    phone: str | None = None
    company: str | None = None
    interest: str
    message: str | None = None

class PartnerForm(BaseModel):
    name: str
    email: str
    company: str
    role: str
    product_type: str
    website: str | None = None
    regions: str | None = None
    message: str | None = None

class ContributorForm(BaseModel):
    name: str
    email: str
    company: str | None = None
    role: str
    assets: str | None = None
    regions: str | None = None
    capacity: str | None = None
    alignment: str | None = None

# --------------------
# DB Setup
# --------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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

    # ✅ CONTRIBUTORS (NEW)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            role TEXT NOT NULL,
            assets TEXT,
            regions TEXT,
            capacity TEXT,
            alignment TEXT,
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

    conn.commit()
    conn.close()

init_db()

# --------------------
# Helpers
# --------------------
def now_iso():
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

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

def require_env():
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

def require_subscriber_token(token: str | None):
    if not token:
        return None, HTMLResponse("Missing token.", status_code=401)

    email = validate_magic_link(token)
    if not email:
        return None, HTMLResponse("Invalid or expired link.", status_code=401)

    if not is_active_subscriber(email):
        return None, HTMLResponse("Subscription not active.", status_code=403)

    return email, None

async def parse_payload(request: Request, Model):
    """
    Accept both:
      - JSON (fetch)
      - form-urlencoded / multipart (plain HTML form)
    """
    ctype = (request.headers.get("content-type") or "").lower()

    if "application/json" in ctype:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    # Normalize empty strings -> None where helpful
    for k, v in list(data.items()):
        if isinstance(v, str) and v.strip() == "":
            data[k] = None

    try:
        return Model(**data), None
    except ValidationError as e:
        return None, JSONResponse({"error": "Validation failed", "detail": e.errors()}, status_code=422)

# --------------------
# Public Pages
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request})

@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request})

@app.post("/lead")
async def submit_lead(request: Request):
    form, err = await parse_payload(request, LeadForm)
    if err:
        return err

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (name, email, phone, company, interest, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (form.name, form.email, form.phone, form.company, form.interest, form.message, now_iso()))
    conn.commit()
    conn.close()
    return {"status": "Lead received"}

@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request})

@app.post("/partner")
async def submit_partner(request: Request):
    form, err = await parse_payload(request, PartnerForm)
    if err:
        return err

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, website, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (form.name, form.email, form.company, form.role, form.product_type, form.website, form.regions, form.message, now_iso()))
    conn.commit()
    conn.close()
    return {"status": "Partner submission received"}

# --------------------
# ✅ Contributor Intake (PUBLIC)
# --------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request})

@app.post("/contributor")
async def submit_contributor(request: Request):
    form, err = await parse_payload(request, ContributorForm)
    if err:
        return err

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contributors (name, email, company, role, assets, regions, capacity, alignment, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (form.name, form.email, form.company, form.role, form.assets, form.regions, form.capacity, form.alignment, now_iso()))
    conn.commit()
    conn.close()

    # Optional internal notification email
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Contributor Submission",
            f"Name: {form.name}\nEmail: {form.email}\nCompany: {form.company}\nRole: {form.role}\n"
            f"Assets: {form.assets}\nRegions: {form.regions}\nCapacity: {form.capacity}\nAlignment: {form.alignment}"
        )

    return {"status": "Contributor submission received"}

# --------------------
# Subscriber Intake (LOCKED)
# --------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str | None = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("intake_form.html", {"request": request, "email": email, "token": token})

@app.post("/intake")
async def submit_intake(request: Request, token: str | None = None):
    email, err = require_subscriber_token(token)
    if err:
        return err

    form, verr = await parse_payload(request, IntakeForm)
    if verr:
        return verr

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (form.name, form.email, form.service_requested, form.notes, now_iso()))
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
def view_intake():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}

# --------------------
# Stripe Checkout
# --------------------
@app.get("/checkout")
def checkout():
    err = require_env()
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

    if session_id and STRIPE_SECRET_KEY:
        try:
            s = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])
            if s and s.get("status") in ("complete", "completed"):
                details = s.get("customer_details") or {}
                email = details.get("email")
                customer_id = s.get("customer")
                subscription_id = s.get("subscription")

                if email:
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
                    """, (email, str(customer_id), str(subscription_id), now_iso(), now_iso()))
                    conn.commit()
                    conn.close()

                    token = issue_magic_link(email, hours=24)

                    if EMAIL_USER and EMAIL_PASS:
                        app_base = str(request.base_url).rstrip("/")
                        link = f"{app_base}/dashboard?token={token}"
                        send_email(
                            email,
                            "Your Nautical Compass Access Link",
                            f"Welcome.\n\nYour access link (valid 24 hours):\n{link}\n"
                        )
        except Exception as e:
            print("Success page Stripe fetch failed:", e)

    return templates.TemplateResponse("success.html", {"request": request, "token": token, "email": email})

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request})

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
        customer_id = session.get("customer")
        customer_email = session.get("customer_details", {}).get("email")
        subscription_id = session.get("subscription")

        if customer_email:
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
            """, (customer_email, str(customer_id), str(subscription_id), now_iso(), now_iso()))
            conn.commit()
            conn.close()

            token = issue_magic_link(customer_email, hours=24)
            app_base = str(request.base_url).rstrip("/")
            link = f"{app_base}/dashboard?token={token}"

            if EMAIL_USER and EMAIL_PASS:
                send_email(
                    customer_email,
                    "Your Nautical Compass Access Link",
                    f"Welcome.\n\nYour access link (valid 24 hours):\n{link}\n"
                )

    if event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        sub_id = sub.get("id")

        conn = db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE subscribers
            SET status='canceled', updated_at=?
            WHERE stripe_subscription_id=?
        """, (now_iso(), str(sub_id)))
        conn.commit()
        conn.close()

    return {"received": True}

# --------------------
# Dashboard (Magic Link Protected)
# --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str | None = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email, "token": token})

# --------------------
# ✅ DEV: Generate token without paying (behind env var)
# --------------------
@app.get("/dev/generate-token")
def dev_generate_token(email: str, hours: int = 24):
    if not DEV_TOKEN_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    token = issue_magic_link(email, hours=hours)
    return {
        "email": email,
        "token": token,
        "dashboard_url": f"/dashboard?token={token}",
        "intake_url": f"/intake-form?token={token}",
    }

# --------------------
# Favicon helper
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
