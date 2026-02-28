# main.py — Nautical Compass (NC) + AVPT + LMT (FULL, CLEAN, LOCKED)
# Adds: AVPT "thanks" page + AVPT admin dashboard + keeps existing rails.

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
from fastapi.responses import (
    HTMLResponse,
    FileResponse,
    RedirectResponse,
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


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
# Env / Config Helpers
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
STRIPE_SPONSOR_PRICE_ID = _clean(os.getenv("STRIPE_SPONSOR_PRICE_ID", ""))  # optional
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


# --------------------
# Email (optional)
# --------------------
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))


# --------------------
# Admin
# --------------------
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))


def require_admin(k: str | None):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set")
    if not k or _clean(k) != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Bad admin key")


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

    # Contributors (fit extract + rail)
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

    # AVPT client requests (Production Company / Event Manager)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS avpt_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            event_name TEXT,
            venue TEXT,
            city TEXT,
            date_start TEXT,
            date_end TEXT,
            crew_needed TEXT,
            gear_needed TEXT,
            budget_range TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # LMT workers (tech / labor intake)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lmt_workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            home_base TEXT,
            roles TEXT,
            experience_level TEXT,
            availability TEXT,
            transport TEXT,
            liftgate_ok TEXT,
            truck_size TEXT,
            certifications TEXT,
            pay_expectation TEXT,
            notes TEXT,
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
        (email, token_hash, expires, now_iso()),
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
        (token_hash,),
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

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)


# --------------------
# Basic pages + assets
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.utcnow().year})


# --------------------
# Lead Intake (Public)
# --------------------
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
    return RedirectResponse("/lead/thanks", status_code=303)


@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return templates.TemplateResponse("lead_thanks.html", {"request": request, "year": datetime.utcnow().year})


# --------------------
# Partner Intake (Public)
# --------------------
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
    if not company.strip():
        company = "N/A"
    if not role.strip():
        role = "N/A"
    if not product_type.strip():
        product_type = "N/A"

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
# Subscriber Intake (NC Legal) — requires token
# --------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("intake_form.html", {"request": request, "email": email, "token": token, "year": datetime.utcnow().year})


@app.post("/intake")
def submit_intake(
    token: str,
    name: str = Form(...),
    email: str = Form(...),
    service_requested: str = Form(...),
    notes: str = Form(""),
):
    sub_email, err = require_subscriber_token(token)
    if err:
        return err

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (name, email, service_requested, notes, now_iso()))
    conn.commit()
    conn.close()

    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber: {sub_email}\n\nName: {name}\nEmail: {email}\nService: {service_requested}\nNotes: {notes}"
        )

    return JSONResponse({"status": "Intake stored successfully"})


@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}


# --------------------
# Option A: /intake/labor -> /lmt/worker
# --------------------
@app.get("/intake/labor")
def intake_labor_redirect():
    return RedirectResponse(url="/lmt/worker", status_code=307)


# --------------------
# AVPT Client Intake (Production / Corporate)
# --------------------
@app.get("/avpt/request", response_class=HTMLResponse)
def avpt_request_page(request: Request):
    return templates.TemplateResponse("avpt_request.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/avpt/request")
def avpt_request_submit(
    org_name: str = Form(...),
    contact_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    event_name: str = Form(""),
    venue: str = Form(""),
    city: str = Form(""),
    date_start: str = Form(""),
    date_end: str = Form(""),
    crew_needed: str = Form(""),
    gear_needed: str = Form(""),
    budget_range: str = Form(""),
    notes: str = Form(""),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO avpt_requests (
            org_name, contact_name, email, phone,
            event_name, venue, city, date_start, date_end,
            crew_needed, gear_needed, budget_range, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        org_name, contact_name, email, phone,
        event_name, venue, city, date_start, date_end,
        crew_needed, gear_needed, budget_range, notes, now_iso()
    ))
    conn.commit()
    conn.close()

    # send internal notification if email is configured
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "AVPT Production Request (New)",
            f"Org: {org_name}\nContact: {contact_name}\nEmail: {email}\nPhone: {phone}\n"
            f"Event: {event_name}\nVenue: {venue}\nCity: {city}\n"
            f"Dates: {date_start} → {date_end}\n"
            f"Crew: {crew_needed}\nGear: {gear_needed}\nBudget: {budget_range}\n"
            f"Notes: {notes}"
        )

    return RedirectResponse("/avpt/thanks", status_code=303)


@app.get("/avpt/thanks", response_class=HTMLResponse)
def avpt_thanks(request: Request):
    return templates.TemplateResponse("avpt_thanks.html", {"request": request, "year": datetime.utcnow().year})


# Admin dashboard so you can SEE the AVPT leads instantly
@app.get("/admin/avpt-dashboard", response_class=HTMLResponse)
def admin_avpt_dashboard(request: Request, k: str | None = None, key: str | None = None):
    require_admin(k or key)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM avpt_requests ORDER BY id DESC LIMIT 500")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "avpt_dashboard.html",
        {"request": request, "rows": rows, "year": datetime.utcnow().year},
    )


# --------------------
# LMT Worker Intake (Labor / Tech)
# --------------------
@app.get("/lmt/worker", response_class=HTMLResponse)
def lmt_worker_page(request: Request):
    return templates.TemplateResponse("lmt_worker.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/lmt/worker")
def lmt_worker_submit(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    home_base: str = Form(""),
    roles: str = Form(""),
    experience_level: str = Form(""),
    availability: str = Form(""),
    transport: str = Form(""),
    liftgate_ok: str = Form(""),
    truck_size: str = Form(""),
    certifications: str = Form(""),
    pay_expectation: str = Form(""),
    notes: str = Form(""),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lmt_workers (
            name, email, phone, home_base, roles, experience_level,
            availability, transport, liftgate_ok, truck_size, certifications,
            pay_expectation, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name, email, phone, home_base, roles, experience_level,
        availability, transport, liftgate_ok, truck_size, certifications,
        pay_expectation, notes, now_iso()
    ))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "Worker profile received"})


# --------------------
# Stripe Checkout
# --------------------
def require_env():
    if STARTUP_URL_ERROR:
        return JSONResponse(
            {"error": STARTUP_URL_ERROR, "hint": "Fix SUCCESS_URL and CANCEL_URL env vars to valid https:// URLs."},
            status_code=500,
        )

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
            metadata={"ref": (ref or "")},
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
            if s:
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
# Dashboard (subscriber)
# --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email, "token": token, "year": datetime.utcnow().year})
