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
# Env helpers
# --------------------
def _clean(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", "").strip()

def _clean_url(s: str) -> str:
    s = _clean(s)
    if s.lower().startswith("value:"):
        s = s.split(":", 1)[1].strip()
    return s

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# --------------------
# Stripe Config
# --------------------
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))
SUCCESS_URL = _clean_url(os.getenv("SUCCESS_URL", ""))
CANCEL_URL = _clean_url(os.getenv("CANCEL_URL", ""))

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# --------------------
# Admin + Dev Token
# --------------------
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))  # use ONE admin key only
DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))

def require_admin(k: str | None):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set")
    if not k or _clean(k) != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Bad admin key")

# --------------------
# Email (optional)
# --------------------
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))

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
# DB
# --------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()

    # Members/legal intake
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

    # Public leads
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            interest TEXT,
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
            company TEXT,
            role TEXT,
            product_type TEXT,
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

    # AVPT/LMT role intakes (the 7 dashboards)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS avpt_intake (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            goal TEXT NOT NULL,
            urgency TEXT NOT NULL,
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
# Models
# --------------------
class IntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: str | None = None

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
# Contributor scoring + rail assignment
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
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)

# --------------------
# Public pages (3-step flow)
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/how-it-works", response_class=HTMLResponse)
def how_it_works(request: Request):
    return templates.TemplateResponse("how_it_works.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/get-access", response_class=HTMLResponse)
def get_access(request: Request):
    return templates.TemplateResponse("get_access.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    return templates.TemplateResponse("dashboards.html", {"request": request, "year": datetime.utcnow().year})

# --------------------
# 7 dashboards
# --------------------
@app.get("/dash/public", response_class=HTMLResponse)
def dash_public(request: Request):
    return templates.TemplateResponse("dash_public.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/dash/tech", response_class=HTMLResponse)
def dash_tech(request: Request):
    return templates.TemplateResponse("dash_tech.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/dash/company", response_class=HTMLResponse)
def dash_company(request: Request):
    return templates.TemplateResponse("dash_company.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/dash/event", response_class=HTMLResponse)
def dash_event(request: Request):
    return templates.TemplateResponse("dash_event.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/dash/rental", response_class=HTMLResponse)
def dash_rental(request: Request):
    return templates.TemplateResponse("dash_rental.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/dash/logistics", response_class=HTMLResponse)
def dash_logistics(request: Request):
    return templates.TemplateResponse("dash_logistics.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/dash/director", response_class=HTMLResponse)
def dash_director(request: Request, k: str | None = None):
    # we pass admin key through so internal links render
    return templates.TemplateResponse("dash_director.html", {"request": request, "year": datetime.utcnow().year, "admin_key": k or ""})

# --------------------
# Role-based intake pages (7)
# --------------------
ROLE_META = {
    "public": ("Public / Consumer", "General users and non-AV visitors."),
    "tech": ("Technician (LMT)", "Labor-side intake: role, skills, availability."),
    "company": ("Production Company (AVPT)", "Company-side intake: staffing needs and execution."),
    "event": ("Corporate Event Manager", "Internal event owner intake."),
    "rental": ("Equipment / Rentals", "Rental partner intake: inventory, holds, delivery windows."),
    "logistics": ("Logistics / Transport", "Driver / routing intake."),
    "director": ("Director / Operator", "Internal operations intake.")
}

@app.get("/intake/{role_key}", response_class=HTMLResponse)
def intake_role(request: Request, role_key: str):
    if role_key not in ROLE_META:
        raise HTTPException(status_code=404, detail="Role not found")

    role_title, role_desc = ROLE_META[role_key]
    return templates.TemplateResponse(
        "intake_role.html",
        {"request": request, "year": datetime.utcnow().year, "role_key": role_key, "role_title": role_title, "role_desc": role_desc}
    )

@app.post("/intake/avpt")
def intake_avpt_submit(
    role: str,
    name: str = Form(...),
    email: str = Form(...),
    company: str = Form(""),
    goal: str = Form(...),
    urgency: str = Form(...),
):
    role = role.strip().lower()
    if role not in ROLE_META:
        return JSONResponse({"error": "Bad role"}, status_code=400)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO avpt_intake (role, name, email, company, goal, urgency, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (role, name, email, company, goal, urgency, now_iso()))
    conn.commit()
    conn.close()

    return {"ok": True, "status": "Intake received", "role": role}

# --------------------
# Public Lead
# --------------------
@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/lead")
def lead_submit(
    name: str = Form(...),
    email: str = Form(...),
    interest: str = Form(""),
    message: str = Form(""),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (name, email, interest, message, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (name, email, interest, message, now_iso()))
    conn.commit()
    conn.close()
    return RedirectResponse("/lead/thanks", status_code=303)

@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return templates.TemplateResponse("lead_thanks.html", {"request": request, "year": datetime.utcnow().year})

# --------------------
# Partner
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
    regions: str = Form(""),
    message: str = Form(""),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, email, company, role, product_type, regions, message, now_iso()))
    conn.commit()
    conn.close()
    return RedirectResponse("/partner/thanks", status_code=303)

@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return templates.TemplateResponse("partner_thanks.html", {"request": request, "year": datetime.utcnow().year})

# --------------------
# Member intake (subscriber-only)
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

    return JSONResponse({"ok": True, "status": "Intake stored successfully"})

@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}

# --------------------
# Stripe Checkout
# --------------------
def require_env():
    missing = []
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_PRICE_ID:
        missing.append("STRIPE_PRICE_ID")
    if not SUCCESS_URL or not (SUCCESS_URL.startswith("https://") or SUCCESS_URL.startswith("http://")):
        missing.append("SUCCESS_URL")
    if not CANCEL_URL or not (CANCEL_URL.startswith("https://") or CANCEL_URL.startswith("http://")):
        missing.append("CANCEL_URL")
    if missing:
        return JSONResponse({"error": "Missing/invalid env vars", "missing": missing}, status_code=500)
    return None

@app.get("/checkout")
def checkout(ref: str | None = None):
    err = require_env()
    if err:
        return err
    try:
        meta = {}
        if ref:
            meta["ref"] = ref

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
            metadata=meta,
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
                        send_email(email, "Your Nautical Compass Access Link", f"{dashboard_link}")
        except Exception as e:
            print("Success fetch failed:", e)

    return templates.TemplateResponse("success.html", {"request": request, "token": token, "email": email, "dashboard_link": dashboard_link, "year": datetime.utcnow().year})

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
def submit_contributor(payload: ContributorForm):
    score = _score_contributor(payload)
    rail = _assign_rail(payload, score)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contributors (
            name, email, phone, company, website,
            primary_role, contribution_track, position_interest, comp_plan, director_owner,
            assets, regions, capacity, alignment, message,
            fit_access, fit_build_goal, fit_opportunity, fit_authority,
            fit_lane, fit_no_conditions, fit_visibility, fit_why_you,
            score, rail, status, created_at
        )
        VALUES (?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?)
    """, (
        payload.name, str(payload.email), payload.phone, payload.company, payload.website,
        payload.primary_role, payload.contribution_track, payload.position_interest, payload.comp_plan, payload.director_owner,
        payload.assets, payload.regions, payload.capacity, payload.alignment, payload.message,
        payload.fit_access, payload.fit_build_goal, payload.fit_opportunity, payload.fit_authority,
        payload.fit_lane, payload.fit_no_conditions, payload.fit_visibility, payload.fit_why_you,
        score, rail, "new", now_iso()
    ))
    conn.commit()
    conn.close()

    return JSONResponse({"ok": True, "status": "Contributor submission received", "rail_assigned": rail, "score": score})

@app.get("/admin/contributors-dashboard", response_class=HTMLResponse)
def contributors_dashboard(request: Request, k: str | None = None, rail: Optional[str] = None, min_score: Optional[int] = None, track: Optional[str] = None):
    require_admin(k)

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

    return templates.TemplateResponse("contributors_dashboard.html", {"request": request, "contributors": rows, "rail": rail, "min_score": min_score, "track": track, "k": k, "year": datetime.utcnow().year})

# --------------------
# Dev token route
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
