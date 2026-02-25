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
# Helpers
# --------------------
def _clean(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", "").strip()

def _clean_url(s: str) -> str:
    s = _clean(s)
    if s.lower().startswith("value:"):
        s = s.split(":", 1)[1].strip()
    return s

def now_iso():
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --------------------
# Env / Config
# --------------------
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

SUCCESS_URL = _clean_url(os.getenv("SUCCESS_URL", ""))
CANCEL_URL = _clean_url(os.getenv("CANCEL_URL", ""))

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))

ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))  # one key, use this everywhere

DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))

# --------------------
# Admin guard
# --------------------
def require_admin(k: str | None):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="Missing ADMIN_KEY env var")
    if not k or _clean(k) != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# --------------------
# Email helper (optional)
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
# Tables
# --------------------
def init_db():
    conn = db()
    cur = conn.cursor()

    # Core intake tables
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

    # Subscriber access rails
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

    # --------------------
    # NEW: Operator Console (Threads + Messages)
    # --------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_type TEXT NOT NULL,         -- lead / partner / intake / sponsor / tow / general
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', -- open / waiting / closed
            priority TEXT NOT NULL DEFAULT 'normal', -- low/normal/high
            contact_name TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            ref_code TEXT,                     -- optional referral/source code
            assigned_to TEXT,                  -- operator email/name
            created_by TEXT,                   -- operator email/name
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS thread_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            direction TEXT NOT NULL,           -- internal / inbound / outbound_draft / outbound_sent
            author TEXT NOT NULL,              -- operator/system/contact
            body TEXT NOT NULL,
            risk_flags TEXT,                   -- comma separated
            created_at TEXT NOT NULL,
            FOREIGN KEY(thread_id) REFERENCES threads(id)
        )
    """)

    conn.commit()
    conn.close()

init_db()

# --------------------
# Magic links
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
# Models (forms)
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
# Contributor scoring
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
# Operator Console: Risk flagging + paste-ready drafts
# --------------------
RISK_PATTERNS = [
    ("guarantee", "Guaranteeing outcomes / results"),
    ("guaranteed", "Guaranteeing outcomes / results"),
    ("we will win", "Outcome certainty claim"),
    ("you will win", "Outcome certainty claim"),
    ("we'll sue", "Legal representation implication"),
    ("we will sue", "Legal representation implication"),
    ("lawsuit", "Threat/Legal escalation language"),
    ("report you", "Threat framing"),
    ("extort", "Threat framing"),
    ("blackmail", "Threat framing"),
    ("i promise", "Promise language"),
    ("100%", "Certainty claim"),
    ("refund you", "Certainty claim about remedy"),
    ("get your money back", "Certainty claim about remedy"),
]

def risk_flags(text: str) -> list[str]:
    t = (text or "").lower()
    hits = []
    for needle, label in RISK_PATTERNS:
        if needle in t:
            hits.append(label)
    # Deduplicate while keeping order
    seen = set()
    out = []
    for h in hits:
        if h not in seen:
            out.append(h)
            seen.add(h)
    return out

def make_safe_outbound(contact_name: str | None, operator_name: str | None, raw: str) -> str:
    """
    Builds a paste-ready message that:
    - avoids guarantees
    - stays informational
    - clarifies scope
    """
    name = (contact_name or "there").strip() or "there"
    op = (operator_name or "Nautical Compass").strip() or "Nautical Compass"
    body = (raw or "").strip()

    header = f"Hi {name} —"
    footer = (
        "\n\n—\n"
        f"{op}\n"
        "Nautical Compass\n"
        "Note: We provide structured information and document organization; outcomes depend on facts and process."
    )
    if not body:
        body = "Quick update: I’m reviewing your details now. What is the single most urgent deadline or outcome you need?"

    return f"{header}\n\n{body}{footer}"

# --------------------
# Public Pages
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
    return {"status": "Lead received"}

@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return templates.TemplateResponse("lead_thanks.html", {"request": request, "year": datetime.utcnow().year})

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
    return {"status": "Partner submission received"}

@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return templates.TemplateResponse("partner_thanks.html", {"request": request, "year": datetime.utcnow().year})

# --------------------
# Subscriber Intake
# --------------------
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

@app.get("/admin/leads-dashboard", response_class=HTMLResponse)
def leads_dashboard(request: Request, k: str | None = None, key: str | None = None):
    require_admin(k or key)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 200")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("leads_dashboard.html", {"request": request, "leads": rows, "k": k or key, "year": datetime.utcnow().year})

# --------------------
# Stripe Checkout
# --------------------
def require_env():
    missing = []
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_PRICE_ID:
        missing.append("STRIPE_PRICE_ID")
    if not SUCCESS_URL or not (SUCCESS_URL.startswith("http://") or SUCCESS_URL.startswith("https://")):
        missing.append("SUCCESS_URL")
    if not CANCEL_URL or not (CANCEL_URL.startswith("http://") or CANCEL_URL.startswith("https://")):
        missing.append("CANCEL_URL")
    if missing:
        return JSONResponse({"error": "Missing/invalid environment variables", "missing": missing}, status_code=500)
    return None

@app.get("/checkout")
def checkout(ref: str | None = None):
    err = require_env()
    if err:
        return err

    try:
        # We keep ref in metadata so you can reconcile later
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
            metadata={"ref": (ref or "")[:64]},
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
# Dashboard
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

    return JSONResponse({"status": "Contributor submission received", "rail_assigned": rail, "score": score})

@app.get("/admin/contributors-dashboard", response_class=HTMLResponse)
def contributors_dashboard(
    request: Request,
    k: str | None = None,
    key: str | None = None,
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
        {"request": request, "contributors": rows, "rail": rail, "min_score": min_score, "track": track, "k": k or key, "year": datetime.utcnow().year},
    )

@app.post("/admin/contributor-status")
def update_contributor_status(id: int, status: str, k: str | None = None, key: str | None = None):
    require_admin(k or key)
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, id))
    conn.commit()
    conn.close()
    return {"ok": True}

# --------------------
# Dev Token Route (for testing)
# --------------------
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
# NEW: Operator Console (Mission Desk)
# --------------------
@app.get("/ops/inbox", response_class=HTMLResponse)
def ops_inbox(request: Request, k: str | None = None, key: str | None = None):
    # Admin-only for now (we can open to operators later with role auth)
    require_admin(k or key)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM threads ORDER BY updated_at DESC LIMIT 200")
    threads = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("ops_inbox.html", {"request": request, "threads": threads, "k": k or key, "year": datetime.utcnow().year})

class NewThread(BaseModel):
    thread_type: str = "general"
    title: str
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    priority: str = "normal"
    assigned_to: str = ""
    ref_code: str = ""
    created_by: str = "system"

@app.get("/ops/new", response_class=HTMLResponse)
def ops_new(request: Request, k: str | None = None, key: str | None = None):
    require_admin(k or key)
    return templates.TemplateResponse("ops_new_thread.html", {"request": request, "k": k or key, "year": datetime.utcnow().year})

@app.post("/ops/new")
def ops_new_post(payload: NewThread, k: str | None = None, key: str | None = None):
    require_admin(k or key)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO threads (thread_type, title, status, priority, contact_name, contact_email, contact_phone, ref_code, assigned_to, created_by, created_at, updated_at)
        VALUES (?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.thread_type.strip()[:40],
        payload.title.strip()[:140],
        payload.priority.strip()[:20],
        payload.contact_name.strip()[:120],
        payload.contact_email.strip()[:160],
        payload.contact_phone.strip()[:50],
        payload.ref_code.strip()[:64],
        payload.assigned_to.strip()[:120],
        payload.created_by.strip()[:120],
        now_iso(),
        now_iso(),
    ))
    thread_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "thread_id": thread_id, "thread_url": f"/ops/thread/{thread_id}?k={_clean(k or key)}"}

@app.get("/ops/thread/{thread_id}", response_class=HTMLResponse)
def ops_thread(request: Request, thread_id: int, k: str | None = None, key: str | None = None):
    require_admin(k or key)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
    thread = cur.fetchone()
    if not thread:
        conn.close()
        raise HTTPException(status_code=404, detail="Thread not found")

    cur.execute("SELECT * FROM thread_messages WHERE thread_id = ? ORDER BY id ASC", (thread_id,))
    messages = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "ops_thread.html",
        {
            "request": request,
            "thread": dict(thread),
            "messages": messages,
            "k": k or key,
            "year": datetime.utcnow().year
        },
    )

class PostMessage(BaseModel):
    direction: str = "internal"  # internal / inbound / outbound_draft / outbound_sent
    author: str = "operator"
    body: str

@app.post("/ops/thread/{thread_id}/message")
def ops_post_message(thread_id: int, payload: PostMessage, k: str | None = None, key: str | None = None):
    require_admin(k or key)

    direction = (payload.direction or "internal").strip()
    author = (payload.author or "operator").strip()
    body = (payload.body or "").strip()

    if not body:
        return JSONResponse({"error": "Message body required"}, status_code=400)

    flags = risk_flags(body)
    flags_csv = ", ".join(flags) if flags else ""

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
    t = cur.fetchone()
    if not t:
        conn.close()
        return JSONResponse({"error": "Thread not found"}, status_code=404)

    cur.execute("""
        INSERT INTO thread_messages (thread_id, direction, author, body, risk_flags, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (thread_id, direction, author, body, flags_csv, now_iso()))

    # bump updated
    cur.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now_iso(), thread_id))

    conn.commit()
    conn.close()

    return {"ok": True, "risk_flags": flags}

@app.post("/ops/thread/{thread_id}/safe-draft")
def ops_safe_draft(thread_id: int, raw: str, operator_name: str = "Operator", k: str | None = None, key: str | None = None):
    """
    Takes raw operator intent and returns a paste-ready outbound message.
    Stores it as outbound_draft automatically so it appears in the thread.
    """
    require_admin(k or key)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
    t = cur.fetchone()
    if not t:
        conn.close()
        return JSONResponse({"error": "Thread not found"}, status_code=404)

    draft = make_safe_outbound(t["contact_name"], operator_name, raw)
    flags = risk_flags(draft)
    flags_csv = ", ".join(flags) if flags else ""

    cur.execute("""
        INSERT INTO thread_messages (thread_id, direction, author, body, risk_flags, created_at)
        VALUES (?, 'outbound_draft', 'system', ?, ?, ?)
    """, (thread_id, draft, flags_csv, now_iso()))
    cur.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now_iso(), thread_id))
    conn.commit()
    conn.close()

    return {"ok": True, "draft": draft, "risk_flags": flags}

@app.post("/ops/thread/{thread_id}/status")
def ops_set_thread_status(thread_id: int, status: str, k: str | None = None, key: str | None = None):
    require_admin(k or key)
    status = (status or "open").strip().lower()
    if status not in ("open", "waiting", "closed"):
        return JSONResponse({"error": "status must be open/waiting/closed"}, status_code=400)

    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE threads SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), thread_id))
    conn.commit()
    conn.close()
    return {"ok": True, "status": status}

# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
