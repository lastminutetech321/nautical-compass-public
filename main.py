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
app = FastAPI(title="Nautical Compass")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --------------------
# Environment Variables
# --------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip().replace("\n", "").replace("\r", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
SUCCESS_URL = os.getenv("SUCCESS_URL", "").strip()
CANCEL_URL = os.getenv("CANCEL_URL", "").strip()

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# --------------------
# Database
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
            name TEXT,
            email TEXT,
            service_requested TEXT,
            notes TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            status TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS magic_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            token_hash TEXT,
            expires_at TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# --------------------
# Helpers
# --------------------
def now():
    return datetime.utcnow().isoformat()

def sha256(s: str):
    return hashlib.sha256(s.encode()).hexdigest()

def issue_magic_link(email: str, hours=24):
    token = secrets.token_urlsafe(32)
    token_hash = sha256(token)
    expires = (datetime.utcnow() + timedelta(hours=hours)).isoformat()

    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO magic_links (email, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (email, token_hash, expires, now())
    )
    conn.commit()
    conn.close()

    return token

def validate_magic_link(token: str):
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

    if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
        return None

    return row["email"]

def is_active(email: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM subscribers WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()
    return row and row["status"] == "active"

def send_email(to, subject, body):
    if not (EMAIL_USER and EMAIL_PASS):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to
        msg.set_content(body)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
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
# Routes
# --------------------
@app.get("/")
def root():
    return {"status": "Nautical Compass Live"}

@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request):
    return templates.TemplateResponse("intake_form.html", {"request": request})

@app.post("/intake")
def submit_intake(form: IntakeForm):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO intake (name,email,service_requested,notes,created_at) VALUES (?,?,?,?,?)",
        (form.name, form.email, form.service_requested, form.notes, now())
    )
    conn.commit()
    conn.close()
    return {"status": "stored"}

# --------------------
# Stripe Checkout
# --------------------
@app.get("/checkout")
def checkout():
    if not STRIPE_PRICE_ID:
        return JSONResponse({"error": "Missing STRIPE_PRICE_ID"}, status_code=500)

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=CANCEL_URL,
    )

    return RedirectResponse(session.url, status_code=303)

@app.get("/success", response_class=HTMLResponse)
def success(request: Request):
    return templates.TemplateResponse("success.html", {"request": request})

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request})

# --------------------
# Webhook
# --------------------
@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session["customer_details"]["email"]
        customer_id = session.get("customer")
        sub_id = session.get("subscription")

        conn = db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO subscribers (email,stripe_customer_id,stripe_subscription_id,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
              stripe_customer_id=excluded.stripe_customer_id,
              stripe_subscription_id=excluded.stripe_subscription_id,
              status='active',
              updated_at=excluded.updated_at
        """, (email, customer_id, sub_id, "active", now(), now()))
        conn.commit()
        conn.close()

        token = issue_magic_link(email)
        link = f"{SUCCESS_URL.replace('/success','')}/dashboard?token={token}"

        send_email(email, "Your Access Link", f"Access: {link}")

    if event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        sub_id = sub["id"]

        conn = db()
        cur = conn.cursor()
        cur.execute("UPDATE subscribers SET status='canceled', updated_at=? WHERE stripe_subscription_id=?",
                    (now(), sub_id))
        conn.commit()
        conn.close()

    return {"received": True}

# --------------------
# Dashboard
# --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str | None = None):
    if not token:
        return HTMLResponse("Missing token.", status_code=401)

    email = validate_magic_link(token)
    if not email:
        return HTMLResponse("Invalid or expired token.", status_code=401)

    if not is_active(email):
        return HTMLResponse("Subscription inactive.", status_code=403)

    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email})
