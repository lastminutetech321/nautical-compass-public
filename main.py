# main.py — Nautical Compass (NC) + AVPT + LMT (FULL, CLEAN, LOCKED)
# Option A implemented: /intake/labor -> redirects to /lmt/worker

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
    # guard against copy-paste like "Value: https://..."
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
# Optional: sponsor tier (if you add later)
STRIPE_SPONSOR_PRICE_ID = _clean(os.getenv("STRIPE_SPONSOR_PRICE_ID", ""))

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

    # AVPT client requests (production companies / event managers)
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
# Contributor scoring + rail assignment (simple v1)
# --------------------
def _score_contributor(track: str, comp_plan: str, assets: str, website: str, company: str,
                      fit_access: str, fit_build_goal: str, fit_opportunity: str, fit_authority: str,
                      fit_lane: str, fit_no_conditions: str, fit_visibility: str, fit_why_you: str) -> int:
    score = 0
    t = (track or "").strip().lower()
    weights = {
        "ecosystem_staff": 18,
        "sales_growth": 18,
        "builder_operator": 16,
        "partner_vendor": 14,
        "hardware_supply": 16,
        "capital_sponsor": 14,
        "advisor_specialist": 10,
        "not_sure": 8,
    }
    score += weights.get(t, 10)

    cp = (comp_plan or "").strip().lower()
    if "residual" in cp or "mrr" in cp:
        score += 10
    elif "commission" in cp:
        score += 10
    elif "hourly" in cp:
        score += 6
    elif "equity" in cp or "revshare" in cp:
        score += 8

    if assets and len(assets.strip()) > 10:
        score += 10
    if website and len(website.strip()) > 6:
        score += 6
    if company and len(company.strip()) > 2:
        score += 4

    fit_fields = [fit_access, fit_build_goal, fit_opportunity, fit_authority,
                  fit_lane, fit_no_conditions, fit_visibility, fit_why_you]
    filled = sum(1 for x in fit_fields if x and str(x).strip())
    score += min(16, filled * 2)

    auth = (fit_authority or "").lower().strip()
    if auth == "owner_exec":
        score += 10
    elif auth == "manager_influence":
        score += 6
    elif auth == "partial":
        score += 3

    return int(score)


def _assign_rail(track: str, position_interest: str, fit_lane: str, score: int) -> str:
    t = (track or "").strip().lower()
    pos = (position_interest or "").strip().lower()
    lane = (fit_lane or "").strip().lower()

    if score >= 70:
        if t == "sales_growth" or lane == "sales" or "sales" in pos or "closer" in pos:
            return "sales_priority"
        if t == "ecosystem_staff" or "intake" in pos or "ops" in pos or "client" in pos:
            return "staff_priority"
        if t == "hardware_supply" or lane == "hardware":
            return "hardware_supply"
        if t == "capital_sponsor" or lane == "finance":
            return "capital"
        return "priority"

    if score >= 45:
        if t == "sales_growth":
            return "sales_pool"
        if t == "ecosystem_staff":
            return "staff_pool"
        if t in ("partner_vendor", "hardware_supply"):
            return "bd_followup"
        return "review"

    return "triage"


# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)


# --------------------
# Public Pages
# --------------------
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
    # If company/role/product_type are required for your UI, enforce here:
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

    # Optional notify admin email
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
# Option A (your choice): /intake/labor -> redirect to /lmt/worker
# --------------------
@app.get("/intake/labor")
def intake_labor_redirect():
    return RedirectResponse(url="/lmt/worker", status_code=307)


# --------------------
# AVPT Client Intake (Production Company / Event Manager)
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
    return RedirectResponse("/services", status_code=303)


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
        # Pass referral code through to Stripe as metadata (so you can credit Duece/operators later)
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
    """
    If Stripe is configured and session_id is present:
      - fetch email
      - mark subscriber active
      - issue token
      - render success.html w/ dashboard_link
    """
    token = None
    email = None
    dashboard_link = None

    if session_id and STRIPE_SECRET_KEY:
        try:
            s = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])
            # Stripe usually returns "complete" or "open"; we accept complete-ish statuses
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


# --------------------
# Contributor Intake + Admin
# --------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/contributor")
def submit_contributor(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    company: str = Form(""),
    website: str = Form(""),

    primary_role: str = Form(...),
    contribution_track: str = Form(...),
    position_interest: str = Form(""),
    comp_plan: str = Form(""),
    director_owner: str = Form("Duece"),

    assets: str = Form(""),
    regions: str = Form(""),
    capacity: str = Form(""),
    alignment: str = Form(""),
    message: str = Form(""),

    fit_access: str = Form(""),
    fit_build_goal: str = Form(""),
    fit_opportunity: str = Form(""),
    fit_authority: str = Form(""),
    fit_lane: str = Form(""),
    fit_no_conditions: str = Form(""),
    fit_visibility: str = Form(""),
    fit_why_you: str = Form(""),
):
    score = _score_contributor(
        contribution_track, comp_plan, assets, website, company,
        fit_access, fit_build_goal, fit_opportunity, fit_authority,
        fit_lane, fit_no_conditions, fit_visibility, fit_why_you
    )
    rail = _assign_rail(contribution_track, position_interest, fit_lane, score)

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
        name, email, phone, company, website,
        primary_role,
        contribution_track, position_interest, comp_plan, director_owner,
        assets, regions, capacity, alignment, message,
        fit_access, fit_build_goal, fit_opportunity, fit_authority,
        fit_lane, fit_no_conditions, fit_visibility, fit_why_you,
        score, rail, "new", now_iso()
    ))
    conn.commit()
    conn.close()

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
    require_admin(k or key)

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
def update_contributor_status(id: int = Form(...), status: str = Form(...), k: str | None = None, key: str | None = None):
    require_admin(k or key)
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, id))
    conn.commit()
    conn.close()
    return {"ok": True}


# --------------------
# Admin Leads Dashboard (simple)
# --------------------
@app.get("/admin/leads-dashboard", response_class=HTMLResponse)
def leads_dashboard(request: Request, k: str | None = None, key: str | None = None):
    require_admin(k or key)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 500")
    leads = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("leads_dashboard.html", {"request": request, "leads": leads, "year": datetime.utcnow().year})


# --------------------
# Dev Token Route (optional)
# --------------------
DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))


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
