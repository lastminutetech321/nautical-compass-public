# main.py — Nautical Compass unified app (FULL FILE)
# Drop in as-is.

import os
import re
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
# Helpers
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

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def year() -> int:
    return datetime.utcnow().year

# --------------------
# Admin / Security
# --------------------
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

def _get_key(k: Optional[str], key: Optional[str]) -> str:
    # support both ?k= and ?key= everywhere
    return _clean(k or key or "")

def require_admin(k: str):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="Missing ADMIN_KEY env var")
    if _clean(k) != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Bad admin key")

# --------------------
# Stripe Config
# --------------------
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

# Optional sponsor checkout (if you use it later)
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

# --------------------
# Email (optional)
# --------------------
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))
SMTP_HOST = _clean(os.getenv("SMTP_HOST", "smtp.gmail.com"))
SMTP_PORT = int(_clean(os.getenv("SMTP_PORT", "465")) or "465")

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

# --------------------
# DB
# --------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --------------------
# People / Referral (NC-only right now)
# --------------------
DUECE_REF = _clean(os.getenv("DUECE_REF", "DEUC46E"))  # your current ref code
DUECE_ID = 1

def make_ref_code(prefix: str) -> str:
    # OP + 5 random chars
    rand = secrets.token_hex(4)[:5].upper()
    return f"{prefix}{rand}"

# --------------------
# Tables
# --------------------
def init_db():
    conn = db()
    cur = conn.cursor()

    # Subscriber intake (member-only)
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

    # Public lead intake
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

    # Partners
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

    # Contributors
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

    # People (operators/staff under Duece)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,          -- 'director' | 'operator' | 'staff'
            ref_code TEXT UNIQUE,        -- referral code
            parent_id INTEGER,           -- Duece is parent for now
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()

    # Ensure Duece exists in people table
    cur.execute("SELECT id FROM people WHERE id = ? LIMIT 1", (DUECE_ID,))
    row = cur.fetchone()
    if not row:
        cur.execute("""
            INSERT INTO people (id, name, email, role, ref_code, parent_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (DUECE_ID, "Duece", "duece@example.com", "director", DUECE_REF, None, now_iso()))
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

    assets = (f.get("assets") or "").strip()
    website = (f.get("website") or "").strip()
    company = (f.get("company") or "").strip()

    if assets and len(assets) > 10:
        score += 10
    if website and len(website) > 6:
        score += 6
    if company and len(company) > 2:
        score += 4

    fit_fields = [
        f.get("fit_access"), f.get("fit_build_goal"), f.get("fit_opportunity"), f.get("fit_authority"),
        f.get("fit_lane"), f.get("fit_no_conditions"), f.get("fit_visibility"), f.get("fit_why_you")
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
# Pages (Public)
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": year()})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": year()})

@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    # This is your Director/Operator landing page (the one in your screenshot)
    return templates.TemplateResponse("dashboards.html", {"request": request, "year": year()})

# --------------------
# Lead Intake (Public)
# --------------------
@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request, "year": year()})

@app.post("/lead")
async def lead_submit(request: Request):
    form = await request.form()
    name = _clean(form.get("name", ""))
    email = _clean(form.get("email", ""))
    interest = _clean(form.get("interest", ""))
    phone = _clean(form.get("phone", ""))
    company = _clean(form.get("company", ""))
    message = _clean(form.get("message", ""))

    if not name or not email:
        return JSONResponse({"error": "Missing name/email"}, status_code=400)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (name, email, phone, company, interest, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, email, phone, company, interest, message, now_iso()))
    conn.commit()
    conn.close()

    return RedirectResponse(url="/lead/thanks", status_code=303)

@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return templates.TemplateResponse("lead_thanks.html", {"request": request, "year": year()})

# --------------------
# Partner Intake
# --------------------
@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request, "year": year()})

@app.post("/partner")
async def partner_submit(request: Request):
    form = await request.form()
    name = _clean(form.get("name", ""))
    email = _clean(form.get("email", ""))
    company = _clean(form.get("company", ""))
    role = _clean(form.get("role", ""))
    product_type = _clean(form.get("product_type", ""))
    website = _clean(form.get("website", ""))
    regions = _clean(form.get("regions", ""))
    message = _clean(form.get("message", ""))

    if not name or not email:
        return JSONResponse({"error": "Missing name/email"}, status_code=400)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, website, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, email, company, role, product_type, website, regions, message, now_iso()))
    conn.commit()
    conn.close()

    return RedirectResponse(url="/partner/thanks", status_code=303)

@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return templates.TemplateResponse("partner_thanks.html", {"request": request, "year": year()})

# --------------------
# Contributor Intake
# --------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": year()})

@app.post("/contributor")
async def submit_contributor(request: Request):
    form = await request.form()

    payload = {
        "name": _clean(form.get("name", "")),
        "email": _clean(form.get("email", "")),
        "phone": _clean(form.get("phone", "")),
        "company": _clean(form.get("company", "")),
        "website": _clean(form.get("website", "")),

        "primary_role": _clean(form.get("primary_role", "")),
        "contribution_track": _clean(form.get("contribution_track", "")),
        "position_interest": _clean(form.get("position_interest", "")),
        "comp_plan": _clean(form.get("comp_plan", "")),
        "director_owner": _clean(form.get("director_owner", "Duece")),

        "assets": _clean(form.get("assets", "")),
        "regions": _clean(form.get("regions", "")),
        "capacity": _clean(form.get("capacity", "")),
        "alignment": _clean(form.get("alignment", "")),
        "message": _clean(form.get("message", "")),

        "fit_access": _clean(form.get("fit_access", "")),
        "fit_build_goal": _clean(form.get("fit_build_goal", "")),
        "fit_opportunity": _clean(form.get("fit_opportunity", "")),
        "fit_authority": _clean(form.get("fit_authority", "")),
        "fit_lane": _clean(form.get("fit_lane", "")),
        "fit_no_conditions": _clean(form.get("fit_no_conditions", "")),
        "fit_visibility": _clean(form.get("fit_visibility", "")),
        "fit_why_you": _clean(form.get("fit_why_you", "")),
    }

    if not payload["name"] or not payload["email"] or not payload["primary_role"] or not payload["contribution_track"]:
        return JSONResponse({"error": "Missing required fields"}, status_code=400)

    score = _score_contributor(payload)
    rail = _assign_rail(payload, score)

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
        payload["name"], payload["email"], payload["phone"], payload["company"], payload["website"],
        payload["primary_role"],
        payload["contribution_track"], payload["position_interest"], payload["comp_plan"], payload["director_owner"],
        payload["assets"], payload["regions"], payload["capacity"], payload["alignment"], payload["message"],
        payload["fit_access"], payload["fit_build_goal"], payload["fit_opportunity"], payload["fit_authority"],
        payload["fit_lane"], payload["fit_no_conditions"], payload["fit_visibility"], payload["fit_why_you"],
        score, rail, "new", now_iso()
    ))
    conn.commit()
    conn.close()

    return JSONResponse({"status": "Contributor submission received", "rail_assigned": rail, "score": score})

# --------------------
# Subscriber Intake (Member-only)
# --------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("intake_form.html", {"request": request, "email": email, "token": token, "year": year()})

@app.post("/intake")
async def submit_intake(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err

    form = await request.form()
    name = _clean(form.get("name", ""))
    public_email = _clean(form.get("email", ""))
    service_requested = _clean(form.get("service_requested", ""))
    notes = _clean(form.get("notes", ""))

    if not name or not public_email or not service_requested:
        return JSONResponse({"error": "Missing required fields"}, status_code=400)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (name, public_email, service_requested, notes, now_iso()))
    conn.commit()
    conn.close()

    # optional notification to you
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber: {email}\n\nName: {name}\nEmail: {public_email}\nService: {service_requested}\nNotes: {notes}"
        )

    return JSONResponse({"status": "Intake stored successfully"})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email, "token": token, "year": year()})

# --------------------
# Stripe Checkout
# --------------------
def require_env():
    if STARTUP_URL_ERROR:
        return JSONResponse(
            {"error": STARTUP_URL_ERROR, "hint": "Fix SUCCESS_URL and CANCEL_URL env vars to valid https:// URLs."},
            status_code=500
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

def _normalize_ref(ref: Optional[str]) -> str:
    ref = _clean(ref or "")
    if not ref:
        return ""
    # allow simple safe chars
    if not re.match(r"^[A-Z0-9]{4,16}$", ref.upper()):
        return ""
    return ref.upper()

@app.get("/checkout")
def checkout(ref: Optional[str] = None):
    err = require_env()
    if err:
        return err

    ref_code = _normalize_ref(ref)
    metadata = {}
    if ref_code:
        metadata["ref"] = ref_code

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
            metadata=metadata,
        )
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

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
        {"request": request, "token": token, "email": email, "dashboard_link": dashboard_link, "year": year()}
    )

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request, "year": year()})

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
# Admin Dashboards (NC)
# --------------------
@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}

@app.get("/admin/leads-dashboard", response_class=HTMLResponse)
def leads_dashboard(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    k2 = _get_key(k, key)
    require_admin(k2)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 200")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "admin_leads.html",
        {"request": request, "leads": rows, "k": k2, "year": year()},
    )

@app.get("/admin/partners-dashboard", response_class=HTMLResponse)
def partners_dashboard(
    request: Request,
    k: Optional[str] = None,
    key: Optional[str] = None,
    q: str = "",
    product: str = "",
    region: str = "",
):
    k2 = _get_key(k, key)
    require_admin(k2)

    q = _clean(q)
    product = _clean(product)
    region = _clean(region)

    conn = db()
    cur = conn.cursor()

    sql = "SELECT * FROM partners WHERE 1=1"
    params = []

    if q:
        sql += " AND (name LIKE ? OR email LIKE ? OR company LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]

    if product:
        sql += " AND product_type LIKE ?"
        params.append(f"%{product}%")

    if region:
        sql += " AND regions LIKE ?"
        params.append(f"%{region}%")

    sql += " ORDER BY id DESC"

    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "partners_dashboard.html",
        {"request": request, "partners": rows, "q": q, "product": product, "region": region, "k": k2, "year": year()},
    )

@app.get("/admin/contributors-dashboard", response_class=HTMLResponse)
def contributors_dashboard(
    request: Request,
    k: Optional[str] = None,
    key: Optional[str] = None,
    rail: Optional[str] = None,
    min_score: Optional[int] = None,
    track: Optional[str] = None,
):
    k2 = _get_key(k, key)
    require_admin(k2)

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
        {"request": request, "contributors": rows, "rail": rail, "min_score": min_score, "track": track, "k": k2, "year": year()},
    )

@app.post("/admin/contributor-status")
async def update_contributor_status(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    k2 = _get_key(k, key)
    require_admin(k2)
    form = await request.form()
    cid = int(form.get("id"))
    status = _clean(form.get("status", ""))

    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, cid))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/admin/people-dashboard", response_class=HTMLResponse)
def people_dashboard(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    k2 = _get_key(k, key)
    require_admin(k2)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people ORDER BY role DESC, id ASC")
    people = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "admin_people.html",
        {"request": request, "people": people, "duece_ref": DUECE_REF, "k": k2, "year": year()},
    )

@app.post("/admin/create-operator")
async def create_operator(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    k2 = _get_key(k, key)
    require_admin(k2)

    form = await request.form()
    name = _clean(form.get("name", ""))
    email = _clean(form.get("email", ""))

    if not name or not email:
        return JSONResponse({"error": "Missing name/email"}, status_code=400)

    ref = make_ref_code("OP")

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO people (name, email, role, ref_code, parent_id, created_at)
        VALUES (?, ?, 'operator', ?, ?, ?)
    """, (name, email, ref, DUECE_ID, now_iso()))
    conn.commit()
    conn.close()

    base = "https://nautical-compass-9rjs6.ondigitalocean.app"
    return {
        "ok": True,
        "ref_code": ref,
        "operator_link": f"{base}/checkout?ref={ref}"
    }

# --------------------
# Dev Token Route (for testing without paying)
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

# --------------------
# Footer pages (Legal + Support)
# --------------------
@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request, "year": year()})

@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request, "year": year()})

@app.get("/privacy-notice", response_class=HTMLResponse)
def privacy_notice_page(request: Request):
    return templates.TemplateResponse("privacy_notice.html", {"request": request, "year": year()})

@app.get("/consumer-privacy-rights", response_class=HTMLResponse)
def consumer_privacy_rights_page(request: Request):
    return templates.TemplateResponse("consumer_privacy_rights.html", {"request": request, "year": year()})

@app.get("/cookie-settings", response_class=HTMLResponse)
def cookie_settings_page(request: Request):
    return templates.TemplateResponse("cookie_settings.html", {"request": request, "year": year()})

@app.get("/accessibility", response_class=HTMLResponse)
def accessibility_page(request: Request):
    return templates.TemplateResponse("accessibility.html", {"request": request, "year": year()})

@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request):
    return templates.TemplateResponse("support.html", {"request": request, "year": year()})

@app.get("/faq", response_class=HTMLResponse)
def faq_page(request: Request):
    return templates.TemplateResponse("faq.html", {"request": request, "year": year()})

@app.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request, "year": year()})

@app.get("/download/ios")
def download_ios():
    return RedirectResponse(url="/", status_code=303)

@app.get("/download/android")
def download_android():
    return RedirectResponse(url="/", status_code=303)

# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
