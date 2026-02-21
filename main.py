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
# Dev-only token route controls
# --------------------
DEV_TOKEN_ENABLED = (os.getenv("DEV_TOKEN_ENABLED", "false") or "false").lower() == "true"
DEV_TOKEN_KEY = (os.getenv("DEV_TOKEN_KEY", "") or "").strip()  # set this to a random secret
DEV_FORCE_ACTIVE = (os.getenv("DEV_FORCE_ACTIVE", "true") or "true").lower() == "true"

# --------------------
# Models (JSON API use only; HTML forms are handled via Form())
# --------------------
class IntakeForm(BaseModel):
    name: str
    email: EmailStr
    service_requested: str
    notes: Optional[str] = None

class LeadForm(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    interest: str
    message: Optional[str] = None

class PartnerForm(BaseModel):
    name: str
    email: EmailStr
    company: str
    role: str
    product_type: str
    website: Optional[str] = None
    regions: Optional[str] = None
    message: Optional[str] = None

class ContributorForm(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    website: Optional[str] = None

    primary_role: str

    # Track routing
    contribution_track: str
    position_interest: Optional[str] = None
    comp_plan: Optional[str] = None
    director_owner: Optional[str] = "Duece"  # user requested spelling

    # Capability / footprint
    assets: Optional[str] = None
    regions: Optional[str] = None
    capacity: Optional[str] = None
    alignment: Optional[str] = None
    message: Optional[str] = None

    # Fit Extract (6–8 questions)
    fit_access: Optional[str] = None
    fit_build_goal: Optional[str] = None
    fit_opportunity: Optional[str] = None
    fit_authority: Optional[str] = None
    fit_lane: Optional[str] = None
    fit_no_conditions: Optional[str] = None
    fit_visibility: Optional[str] = None
    fit_why_you: Optional[str] = None

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

    # --------------------
    # Contributors (NEW)
    # --------------------
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

    conn.commit()
    conn.close()

init_db()

# --------------------
# Helpers (Auth + Tokens)
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
# Contributor Scoring / Rails (NEW)
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
async def submit_lead(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    interest: str = Form(...),
    phone: Optional[str] = Form(None),
    company: Optional[str] = Form(None),
    message: Optional[str] = Form(None),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (name, email, phone, company, interest, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, email, phone, company, interest, message, now_iso()))
    conn.commit()
    conn.close()

    return templates.TemplateResponse("lead_intake.html", {
        "request": request,
        "year": datetime.utcnow().year,
        "submitted": True
    })

@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/partner")
async def submit_partner(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    company: str = Form(...),
    role: str = Form(...),
    product_type: str = Form(...),
    website: Optional[str] = Form(None),
    regions: Optional[str] = Form(None),
    message: Optional[str] = Form(None),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, website, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, email, company, role, product_type, website, regions, message, now_iso()))
    conn.commit()
    conn.close()

    return templates.TemplateResponse("partner_intake.html", {
        "request": request,
        "year": datetime.utcnow().year,
        "submitted": True
    })

# --------------------
# Contributor Intake (NEW)
# --------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/contributor")
async def submit_contributor(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    company: Optional[str] = Form(None),
    website: Optional[str] = Form(None),

    primary_role: str = Form(...),

    contribution_track: str = Form(...),
    position_interest: Optional[str] = Form(None),
    comp_plan: Optional[str] = Form(None),
    director_owner: Optional[str] = Form("Duece"),

    assets: Optional[str] = Form(None),
    regions: Optional[str] = Form(None),
    capacity: Optional[str] = Form(None),
    alignment: Optional[str] = Form(None),
    message: Optional[str] = Form(None),

    fit_access: Optional[str] = Form(None),
    fit_build_goal: Optional[str] = Form(None),
    fit_opportunity: Optional[str] = Form(None),
    fit_authority: Optional[str] = Form(None),
    fit_lane: Optional[str] = Form(None),
    fit_no_conditions: Optional[str] = Form(None),
    fit_visibility: Optional[str] = Form(None),
    fit_why_you: Optional[str] = Form(None),
):
    form_obj = ContributorForm(
        name=name,
        email=email,
        phone=phone,
        company=company,
        website=website,
        primary_role=primary_role,
        contribution_track=contribution_track,
        position_interest=position_interest,
        comp_plan=comp_plan,
        director_owner=director_owner,
        assets=assets,
        regions=regions,
        capacity=capacity,
        alignment=alignment,
        message=message,
        fit_access=fit_access,
        fit_build_goal=fit_build_goal,
        fit_opportunity=fit_opportunity,
        fit_authority=fit_authority,
        fit_lane=fit_lane,
        fit_no_conditions=fit_no_conditions,
        fit_visibility=fit_visibility,
        fit_why_you=fit_why_you
    )

    score = _score_contributor(form_obj)
    rail = _assign_rail(form_obj, score)

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

    return templates.TemplateResponse("contributor_intake.html", {
        "request": request,
        "year": datetime.utcnow().year,
        "submitted": True,
        "rail": rail,
        "score": score
    })

# --------------------
# Subscriber Intake (Magic Link Protected)
# --------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: Optional[str] = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("intake_form.html", {
        "request": request, "year": datetime.utcnow().year, "email": email, "token": token
    })

@app.post("/intake")
async def submit_intake(
    request: Request,
    token: Optional[str] = None,
    name: str = Form(...),
    email: str = Form(...),
    service_requested: str = Form(...),
    notes: Optional[str] = Form(None),
):
    subscriber_email, err = require_subscriber_token(token)
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

    # Optional internal email
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber: {subscriber_email}\n\nName: {name}\nEmail: {email}\nService: {service_requested}\nNotes: {notes}"
        )

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "year": datetime.utcnow().year,
        "email": subscriber_email,
        "token": token,
        "intake_submitted": True
    })

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: Optional[str] = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "year": datetime.utcnow().year, "email": email, "token": token})

@app.get("/admin/intake")
def view_intake():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC")
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
                    upsert_subscriber_active(email, str(customer_id), str(subscription_id))
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

    app_base = str(request.base_url).rstrip("/")
    dashboard_link = f"{app_base}/dashboard?token={token}" if token else None
    intake_link = f"{app_base}/intake-form?token={token}" if token else None

    return templates.TemplateResponse("success.html", {
        "request": request,
        "year": datetime.utcnow().year,
        "token": token,
        "email": email,
        "dashboard_link": dashboard_link,
        "intake_link": intake_link
    })

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
        customer_id = session.get("customer")
        customer_email = session.get("customer_details", {}).get("email")
        subscription_id = session.get("subscription")

        if customer_email:
            upsert_subscriber_active(customer_email, str(customer_id), str(subscription_id))

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
# Dev-only token generator (NEW)
# --------------------
@app.get("/dev/generate-token")
def dev_generate_token(email: str, key: str = ""):
    """
    Usage:
    /dev/generate-token?email=you@example.com&key=YOUR_DEV_TOKEN_KEY
    """
    if not DEV_TOKEN_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

    # If a key is set, require it
    if DEV_TOKEN_KEY and key != DEV_TOKEN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    if DEV_FORCE_ACTIVE:
        upsert_subscriber_active(email, "", "")

    token = issue_magic_link(email, hours=24)
    return {
        "email": email,
        "token": token,
        "dashboard": f"/dashboard?token={token}",
        "intake_form": f"/intake-form?token={token}"
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
