import os
import sqlite3
import smtplib
import hashlib
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

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
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --------------------
# Stripe Config
# --------------------
def _clean_env(name: str) -> str:
    # Strip whitespace + remove any accidental newlines that break headers
    return (os.getenv(name) or "").strip().replace("\n", "").replace("\r", "")

STRIPE_SECRET_KEY = _clean_env("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = _clean_env("STRIPE_PRICE_ID")
SUCCESS_URL = _clean_env("SUCCESS_URL")
CANCEL_URL = _clean_env("CANCEL_URL")
STRIPE_WEBHOOK_SECRET = _clean_env("STRIPE_WEBHOOK_SECRET")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# --------------------
# Email (Mailgun SMTP)
# --------------------
EMAIL_USER = (os.getenv("EMAIL_USER") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").strip()

SMTP_HOST = (os.getenv("SMTP_HOST") or "smtp.mailgun.org").strip()
SMTP_PORT = int((os.getenv("SMTP_PORT") or "587").strip())

def send_email(to_email: str, subject: str, body: str):
    # If email creds are missing, just skip (never crash the app)
    if not (EMAIL_USER and EMAIL_PASS):
        return

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg.set_content(body)

        # Mailgun SMTP: STARTTLS on 587
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)

    except Exception as e:
        print("Email failed:", e)

# --------------------
# Models
# --------------------
class IntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: str | None = None

# --------------------
# DB Setup
# --------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso():
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
# Magic Links
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

# --------------------
# Helpers
# --------------------
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
    if not STRIPE_WEBHOOK_SECRET:
        missing.append("STRIPE_WEBHOOK_SECRET")

    if missing:
        return JSONResponse({"error": "Missing environment variables", "missing": missing}, status_code=500)
    return None

# --------------------
# Routes
# --------------------
@app.get("/")
def root():
    return {"message": "Nautical Compass is live"}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)

@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request):
    return templates.TemplateResponse("intake_form.html", {"request": request})

@app.post("/intake")
def submit_intake(form: IntakeForm):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (form.name, form.email, form.service_requested, form.notes, now_iso()))
    conn.commit()
    conn.close()

    # Optional internal notification email
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Intake Submission",
            f"Name: {form.name}\nEmail: {form.email}\nService: {form.service_requested}\nNotes: {form.notes}"
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
def success(request: Request):
    return templates.TemplateResponse("success.html", {"request": request})

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request})

# --------------------
# Stripe Webhook (GRANTS ACCESS)
# --------------------
@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    err = require_env()
    if err:
        # If env missing, return JSON (Stripe will see non-2xx)
        raise HTTPException(status_code=500, detail="Missing required environment variables")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook signature error: {e}")

    # 1) checkout.session.completed = payment done
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        customer_id = session.get("customer")
        customer_email = session.get("customer_details", {}).get("email")
        subscription_id = session.get("subscription")

        if customer_email:
            conn = db()
            cur = conn.cursor()

            # Upsert subscriber
            cur.execute("""
                INSERT INTO subscribers (email, stripe_customer_id, stripe_subscription_id, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                  stripe_customer_id=excluded.stripe_customer_id,
                  stripe_subscription_id=excluded.stripe_subscription_id,
                  status='active',
                  updated_at=excluded.updated_at
            """, (customer_email, customer_id, subscription_id, now_iso(), now_iso()))
            conn.commit()
            conn.close()

            # Issue magic link + email it
            token = issue_magic_link(customer_email, hours=24)
            app_base = str(request.base_url).rstrip("/")
            link = f"{app_base}/dashboard?token={token}"

            send_email(
                customer_email,
                "Your Nautical Compass Access Link",
                f"Welcome.\n\nYour access link (valid 24 hours):\n{link}\n\nIf it expires, contact support."
            )

    # 2) subscription canceled
    if event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        sub_id = sub.get("id")

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

# --------------------
# Dashboard (Magic Link Protected)
# --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str | None = None):
    if not token:
        return HTMLResponse("Missing token.", status_code=401)

    email = validate_magic_link(token)
    if not email:
        return HTMLResponse("Invalid or expired link.", status_code=401)

    if not is_active_subscriber(email):
        return HTMLResponse("Subscription not active.", status_code=403)

    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email})
