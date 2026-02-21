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
# Stripe Config
# --------------------
STRIPE_SECRET_KEY = (os.getenv("STRIPE_SECRET_KEY") or "").strip().replace("\n", "").replace("\r", "")
STRIPE_PRICE_ID = (os.getenv("STRIPE_PRICE_ID") or "").strip()
SUCCESS_URL = (os.getenv("SUCCESS_URL") or "").strip()
CANCEL_URL = (os.getenv("CANCEL_URL") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


# --------------------
# Email (optional)
# --------------------
EMAIL_USER = (os.getenv("EMAIL_USER") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").strip()

# If you switched to Mailgun SMTP, set these env vars and the app will use them:
SMTP_HOST = (os.getenv("SMTP_HOST") or "").strip()         # e.g. smtp.mailgun.org
SMTP_PORT = int(os.getenv("SMTP_PORT") or "0")             # e.g. 587
SMTP_USER = (os.getenv("SMTP_USER") or "").strip()         # your mailgun smtp login
SMTP_PASS = (os.getenv("SMTP_PASS") or "").strip()         # your mailgun smtp password
SMTP_FROM = (os.getenv("SMTP_FROM") or EMAIL_USER).strip() # from address


# --------------------
# Dev Tools (optional)
# --------------------
DEV_TOOLS_ENABLED = (os.getenv("DEV_TOOLS_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")
DEV_TOOLS_KEY = (os.getenv("DEV_TOOLS_KEY") or "").strip()  # optional shared secret for dev routes


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

    # Subscriber intake
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

    # Partner/vendor intake
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

    # Contributors (staff/sales/builders)
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

    # Subscribers
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


def upsert_subscriber_active(email: str, customer_id: Optional[str] = None, subscription_id: Optional[str] = None):
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


def cancel_subscriber_by_sub_id(sub_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE subscribers
        SET status='canceled', updated_at=?
        WHERE stripe_subscription_id=?
    """, (now_iso(), sub_id))
    conn.commit()
    conn.close()


def send_email(to_email: str, subject: str, body: str):
    """
    Uses Mailgun SMTP if SMTP_HOST/PORT/USER/PASS are set,
    otherwise falls back to Gmail SSL if EMAIL_USER/EMAIL_PASS exist.
    """
    try:
        # Mailgun / generic SMTP (recommended)
        if SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = SMTP_FROM or SMTP_USER
            msg["To"] = to_email
            msg.set_content(body)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.starttls()
                smtp.login(SMTP_USER, SMTP_PASS)
                smtp.send_message(msg)
            return

        # Gmail SSL fallback
        if EMAIL_USER and EMAIL_PASS:
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


def require_subscriber_token(token: Optional[str]) -> Tuple[Optional[str], Optional[HTMLResponse]]:
    if not token:
        return None, HTMLResponse("Missing token.", status_code=401)

    email = validate_magic_link(token)
    if not email:
        return None, HTMLResponse("Invalid or expired link.", status_code=401)

    if not is_active_subscriber(email):
        return None, HTMLResponse("Subscription not active.", status_code=403)

    return email, None


async def read_payload(request: Request) -> dict:
    """
    Accept both:
      - application/json (fetch)
      - application/x-www-form-urlencoded or multipart (HTML forms)
    """
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            return await request.json()
        except Exception:
            return {}
    form = await request.form()
    return dict(form)


# --------------------
# Contributor scoring + rail assignment
# --------------------
def _score_contributor(f: dict) -> int:
    score = 0
    track = (f.get("contribution_track") or "").strip().lower()

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

    comp = (f.get("comp_plan") or "").strip().lower()
    if "residual" in comp:
        score += 10
    elif "commission" in comp:
        score += 10
    elif "hourly" in comp:
        score += 6
    elif "equity" in comp or "revshare" in comp:
        score += 8

    if (f.get("assets") or "").strip():
        score += 10
    if (f.get("website") or "").strip():
        score += 6
    if (f.get("company") or "").strip():
        score += 4

    fit_fields = [
        f.get("fit_access"),
        f.get("fit_build_goal"),
        f.get("fit_opportunity"),
        f.get("fit_authority"),
        f.get("fit_lane"),
        f.get("fit_no_conditions"),
        f.get("fit_visibility"),
        f.get("fit_why_you"),
    ]
    filled = sum(1 for x in fit_fields if x and str(x).strip())
    score += min(16, filled * 2)

    auth = (f.get("fit_authority") or "").lower().strip()
    if auth == "owner_exec":
        score += 10
    elif auth == "manager_influence":
        score += 6
    elif auth == "partial":
        score += 3

    return int(score)


def _assign_rail(f: dict, score: int) -> str:
    track = (f.get("contribution_track") or "").strip().lower()
    pos = (f.get("position_interest") or "").strip().lower()
    lane = (f.get("fit_lane") or "").strip().lower()

    if score >= 70:
        if track == "sales_growth" or lane == "sales" or "sales" in pos or "closer" in pos:
            return "sales_priority"
        if track == "ecosystem_staff" or "intake" in pos or "ops" in pos or "client_success" in pos:
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
# Pages (Public)
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/services", response_class=HTMLResponse)
def services_page(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": datetime.utcnow().year})


# --------------------
# Public submits
# --------------------
@app.post("/lead")
async def submit_lead(request: Request):
    data = await read_payload(request)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    interest = (data.get("interest") or "").strip()

    if not (name and email and interest):
        return JSONResponse({"error": "Missing required fields"}, status_code=422)

    phone = (data.get("phone") or "").strip() or None
    company = (data.get("company") or "").strip() or None
    message = (data.get("message") or "").strip() or None

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (name, email, phone, company, interest, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, email, phone, company, interest, message, now_iso()))
    conn.commit()
    conn.close()

    return JSONResponse({"status": "Lead received"})


@app.post("/partner")
async def submit_partner(request: Request):
    data = await read_payload(request)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    company = (data.get("company") or "").strip()
    role = (data.get("role") or "").strip()
    product_type = (data.get("product_type") or "").strip()

    if not (name and email and company and role and product_type):
        return JSONResponse({"error": "Missing required fields"}, status_code=422)

    website = (data.get("website") or "").strip() or None
    regions = (data.get("regions") or "").strip() or None
    message = (data.get("message") or "").strip() or None

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, website, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, email, company, role, product_type, website, regions, message, now_iso()))
    conn.commit()
    conn.close()

    return JSONResponse({"status": "Partner submission received"})


@app.post("/contributor")
async def submit_contributor(request: Request):
    data = await read_payload(request)

    # required
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    primary_role = (data.get("primary_role") or "").strip()
    contribution_track = (data.get("contribution_track") or "").strip()

    if not (name and email and primary_role and contribution_track):
        return JSONResponse({"error": "Missing required fields"}, status_code=422)

    # score + rail
    score = _score_contributor(data)
    rail = _assign_rail(data, score)

    # optional
    phone = (data.get("phone") or "").strip() or None
    company = (data.get("company") or "").strip() or None
    website = (data.get("website") or "").strip() or None
    position_interest = (data.get("position_interest") or "").strip() or None
    comp_plan = (data.get("comp_plan") or "").strip() or None
    director_owner = (data.get("director_owner") or "Deuce").strip() or "Deuce"

    assets = (data.get("assets") or "").strip() or None
    regions = (data.get("regions") or "").strip() or None
    capacity = (data.get("capacity") or "").strip() or None
    alignment = (data.get("alignment") or "").strip() or None
    message = (data.get("message") or "").strip() or None

    fit_access = (data.get("fit_access") or "").strip() or None
    fit_build_goal = (data.get("fit_build_goal") or "").strip() or None
    fit_opportunity = (data.get("fit_opportunity") or "").strip() or None
    fit_authority = (data.get("fit_authority") or "").strip() or None
    fit_lane = (data.get("fit_lane") or "").strip() or None
    fit_no_conditions = (data.get("fit_no_conditions") or "").strip() or None
    fit_visibility = (data.get("fit_visibility") or "").strip() or None
    fit_why_you = (data.get("fit_why_you") or "").strip() or None

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


# --------------------
# Subscriber Intake (Token gated)
# --------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: Optional[str] = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse(
        "intake_form.html",
        {"request": request, "email": email, "token": token, "year": datetime.utcnow().year},
    )


@app.post("/intake")
async def submit_intake(request: Request, token: Optional[str] = None):
    email, err = require_subscriber_token(token)
    if err:
        return err

    data = await read_payload(request)
    name = (data.get("name") or "").strip()
    user_email = (data.get("email") or "").strip()
    service_requested = (data.get("service_requested") or "").strip()
    notes = (data.get("notes") or "").strip() or None

    if not (name and user_email and service_requested):
        return JSONResponse({"error": "Missing required fields"}, status_code=422)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (name, user_email, service_requested, notes, now_iso()))
    conn.commit()
    conn.close()

    # Optional internal notification
    if (SMTP_HOST and SMTP_USER and SMTP_PASS) or (EMAIL_USER and EMAIL_PASS):
        send_email(
            SMTP_FROM or EMAIL_USER or user_email,
            "New Subscriber Intake Submission",
            f"Authorized subscriber: {email}\n\nName: {name}\nEmail: {user_email}\nService: {service_requested}\nNotes: {notes}"
        )

    return JSONResponse({"status": "Intake stored successfully"})


# --------------------
# Admin readouts (simple)
# --------------------
@app.get("/admin/intake")
def view_intake():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}


@app.get("/admin/leads")
def view_leads():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}


@app.get("/admin/partners")
def view_partners():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM partners ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}


@app.get("/admin/contributors")
def view_contributors():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM contributors ORDER BY id DESC")
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
def success(request: Request, session_id: Optional[str] = None):
    """
    Success page creates a token too (so you are NOT dependent on email being configured).
    """
    token = None
    email = None
    dashboard_link = None

    if session_id and STRIPE_SECRET_KEY:
        try:
            s = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])
            details = s.get("customer_details") or {}
            email = details.get("email")

            # Stripe can return "complete" for status on Checkout
            if email and (s.get("status") in ("complete", "completed")):
                customer_id = str(s.get("customer") or "")
                subscription_id = str(s.get("subscription") or "")
                upsert_subscriber_active(email, customer_id=customer_id, subscription_id=subscription_id)

                token = issue_magic_link(email, hours=24)
                app_base = str(request.base_url).rstrip("/")
                dashboard_link = f"{app_base}/dashboard?token={token}"

                # Email the access link too (if configured)
                if (SMTP_HOST and SMTP_USER and SMTP_PASS) or (EMAIL_USER and EMAIL_PASS):
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

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = str(session.get("customer") or "")
        customer_email = (session.get("customer_details", {}) or {}).get("email")
        subscription_id = str(session.get("subscription") or "")

        if customer_email:
            upsert_subscriber_active(customer_email, customer_id=customer_id, subscription_id=subscription_id)

            token = issue_magic_link(customer_email, hours=24)
            app_base = str(request.base_url).rstrip("/")
            link = f"{app_base}/dashboard?token={token}"

            if (SMTP_HOST and SMTP_USER and SMTP_PASS) or (EMAIL_USER and EMAIL_PASS):
                send_email(
                    customer_email,
                    "Your Nautical Compass Access Link",
                    f"Welcome.\n\nYour access link (valid 24 hours):\n{link}\n"
                )

    if event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        sub_id = str(sub.get("id") or "")
        if sub_id:
            cancel_subscriber_by_sub_id(sub_id)

    return {"received": True}


# --------------------
# Dashboard (Magic Link Protected)
# --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: Optional[str] = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "email": email, "token": token, "year": datetime.utcnow().year},
    )


# --------------------
# Dev: Generate token (NO PAY) — OPTIONAL
# --------------------
@app.get("/dev/generate-token")
def dev_generate_token(email: str, key: Optional[str] = None):
    """
    Usage:
      /dev/generate-token?email=you@example.com
    Optional lock:
      set DEV_TOOLS_KEY, then call:
      /dev/generate-token?email=you@example.com&key=YOURKEY

    Behavior:
      - marks subscriber ACTIVE for that email
      - issues a 24h magic link
      - redirects to /dashboard?token=...
    """
    if not DEV_TOOLS_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")

    if DEV_TOOLS_KEY and (key or "") != DEV_TOOLS_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    email = (email or "").strip()
    if not email:
        raise HTTPException(status_code=422, detail="email is required")

    upsert_subscriber_active(email, customer_id="DEV", subscription_id="DEV")
    token = issue_magic_link(email, hours=24)
    return RedirectResponse(url=f"/dashboard?token={token}", status_code=303)


# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
