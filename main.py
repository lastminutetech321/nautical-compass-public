import os
import sqlite3
import smtplib
import hashlib
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Tuple

import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

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
app = FastAPI(title="Nautical Compass Intake")

# Static + Templates (won't crash if folder exists but empty)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --------------------
# Stripe Config
# --------------------
STRIPE_SECRET_KEY = (os.getenv("STRIPE_SECRET_KEY", "") or "").strip().replace("\n", "").replace("\r", "")
STRIPE_PRICE_ID = (os.getenv("STRIPE_PRICE_ID", "") or "").strip()
SUCCESS_URL = (os.getenv("SUCCESS_URL", "") or "").strip()
CANCEL_URL = (os.getenv("CANCEL_URL", "") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET", "") or "").strip()

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# --------------------
# Email (optional)
# --------------------
EMAIL_USER = (os.getenv("EMAIL_USER") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").strip()

# --------------------
# Models
# --------------------
class IntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: Optional[str] = None

class LeadForm(BaseModel):
    name: str
    email: str
    interest: str
    phone: Optional[str] = None
    company: Optional[str] = None
    message: Optional[str] = None

class PartnerForm(BaseModel):
    name: str
    email: str
    company: str
    role: str
    product_type: str
    website: Optional[str] = None
    regions: Optional[str] = None
    message: Optional[str] = None

# --------------------
# DB
# --------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso() -> str:
    return datetime.utcnow().isoformat()

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

    conn.commit()
    conn.close()

init_db()

# --------------------
# Helpers
# --------------------
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

def send_email(to_email: str, subject: str, body: str):
    # Optional; never crash the app if email isn't configured
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

def require_env_for_checkout() -> Optional[JSONResponse]:
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

def require_subscriber_token(token: Optional[str]) -> Tuple[Optional[str], Optional[HTMLResponse]]:
    if not token:
        return None, HTMLResponse("Missing token.", status_code=401)

    email = validate_magic_link(token)
    if not email:
        return None, HTMLResponse("Invalid or expired link.", status_code=401)

    if not is_active_subscriber(email):
        return None, HTMLResponse("Subscription not active.", status_code=403)

    return email, None

def template_or_fallback(request: Request, name: str, ctx: dict) -> HTMLResponse:
    # If a template name is wrong/missing, show a clean message instead of crashing the app
    try:
        return templates.TemplateResponse(name, ctx)
    except Exception as e:
        print(f"Template render failed: {name} -> {e}")
        return HTMLResponse(
            f"<h1>Nautical Compass</h1><p>Template error: {name}</p><p>{str(e)}</p>",
            status_code=200
        )

# --------------------
# Public Pages
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return template_or_fallback(request, "index.html", {"request": request})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return template_or_fallback(request, "services.html", {"request": request})

@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return template_or_fallback(request, "lead_intake.html", {"request": request})

@app.post("/lead")
def submit_lead(form: LeadForm):
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
    return template_or_fallback(request, "partner_intake.html", {"request": request})

@app.post("/partner")
def submit_partner(form: PartnerForm):
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
# Subscriber Intake (token protected)
# --------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: Optional[str] = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return template_or_fallback(request, "intake_form.html", {"request": request, "email": email, "token": token})

@app.post("/intake")
def submit_intake(form: IntakeForm, token: Optional[str] = None):
    email, err = require_subscriber_token(token)
    if err:
        return err

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (form.name, form.email, form.service_requested, form.notes, now_iso()))
    conn.commit()
    conn.close()

    # Optional internal notify
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
    err = require_env_for_checkout()
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
    """
    Always renders cleanly.
    If Stripe is configured + paid session_id is provided, it will:
      - mark subscriber active
      - generate token
      - show token link on page (and email it if configured)
    """
    token = None
    email = None
    dashboard_link = None

    # Render even if Stripe not configured
    if session_id and STRIPE_SECRET_KEY:
        try:
            s = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])

            # Stripe signals:
            # - s.status == "complete"
            # - s.payment_status == "paid"
            status = getattr(s, "status", None) if not isinstance(s, dict) else s.get("status")
            pay_status = getattr(s, "payment_status", None) if not isinstance(s, dict) else s.get("payment_status")

            # Customer email
            customer_details = getattr(s, "customer_details", None) if not isinstance(s, dict) else s.get("customer_details")
            if not customer_details:
                customer_details = {}

            email = customer_details.get("email")

            # IDs (handles expanded or not)
            customer_obj = getattr(s, "customer", None) if not isinstance(s, dict) else s.get("customer")
            subscription_obj = getattr(s, "subscription", None) if not isinstance(s, dict) else s.get("subscription")

            customer_id = customer_obj.get("id") if isinstance(customer_obj, dict) else str(customer_obj) if customer_obj else None
            subscription_id = subscription_obj.get("id") if isinstance(subscription_obj, dict) else str(subscription_obj) if subscription_obj else None

            is_paid = (pay_status == "paid") or (status == "complete")

            if is_paid and email:
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

                token = issue_magic_link(email, hours=24)
                app_base = str(request.base_url).rstrip("/")
                dashboard_link = f"{app_base}/dashboard?token={token}"

                # Email the subscriber (optional)
                if EMAIL_USER and EMAIL_PASS:
                    send_email(
                        email,
                        "Your Nautical Compass Access Link",
                        f"Welcome.\n\nYour access link (valid 24 hours):\n{dashboard_link}\n"
                    )
        except Exception as e:
            # Never fail the page render
            print("Success page Stripe fetch failed:", e)

    return template_or_fallback(
        request,
        "success.html",
        {"request": request, "token": token, "email": email, "dashboard_link": dashboard_link}
    )

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return template_or_fallback(request, "cancel.html", {"request": request})

# --------------------
# Stripe Webhook (GRANTS ACCESS)
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

    etype = event.get("type")

    if etype == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = (session.get("customer_details") or {}).get("email")
        customer_id = session.get("customer")
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

    elif etype == "customer.subscription.deleted":
        sub = event["data"]["object"]
        sub_id = sub.get("id")
        if sub_id:
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
def dashboard(request: Request, token: Optional[str] = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return template_or_fallback(request, "dashboard.html", {"request": request, "email": email, "token": token})

# --------------------
# Favicon helper
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
