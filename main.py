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
# Admin / Dev
# --------------------
ADMIN_KEY = (os.getenv("ADMIN_KEY", "") or "").strip()  # required to view admin routes
DEV_MODE = (os.getenv("DEV_MODE", "0") or "0").strip()  # "1" enables dev routes
DEV_TOKEN_SECRET = (os.getenv("DEV_TOKEN_SECRET", "") or "").strip()

# --------------------
# Email (optional) - can be Mailgun SMTP or Gmail SMTP
# --------------------
EMAIL_USER = (os.getenv("EMAIL_USER") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").strip()
SMTP_HOST = (os.getenv("SMTP_HOST") or "").strip() or "smtp.mailgun.org"
SMTP_PORT = int((os.getenv("SMTP_PORT") or "587").strip())
SMTP_USE_SSL = (os.getenv("SMTP_USE_SSL") or "0").strip() == "1"  # set 1 if using SSL:465

# --------------------
# Models
# --------------------
class IntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: str | None = None

class LeadForm(BaseModel):
    name: str
    email: str
    phone: str | None = None
    company: str | None = None
    interest: str
    message: str | None = None

class PartnerForm(BaseModel):
    name: str
    email: str
    company: str
    role: str
    product_type: str
    website: str | None = None
    regions: str | None = None
    message: str | None = None

class ContributorForm(BaseModel):
    name: str
    email: str
    company: str | None = None
    role: str
    assets: str | None = None
    regions: str | None = None
    capacity: str | None = None
    alignment: str | None = None

# --------------------
# DB Helpers
# --------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso():
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def send_email(to_email: str, subject: str, body: str):
    """Optional notifications + links. Works with Mailgun SMTP or Gmail SMTP."""
    if not (EMAIL_USER and EMAIL_PASS):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg.set_content(body)

        if SMTP_USE_SSL:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.starttls()
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)

# --------------------
# DB Init
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

    # Subscribers (paid users)
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

    # Contributors (manufacturers/operators/etc.)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            role TEXT NOT NULL,
            assets TEXT,
            regions TEXT,
            capacity TEXT,
            alignment TEXT,
            status TEXT NOT NULL DEFAULT 'new',  -- new|reviewed|approved|rejected
            nda_accepted_at TEXT,
            score_total INTEGER NOT NULL DEFAULT 0,
            score_role_fit INTEGER NOT NULL DEFAULT 0,
            score_assets INTEGER NOT NULL DEFAULT 0,
            score_region INTEGER NOT NULL DEFAULT 0,
            score_capacity INTEGER NOT NULL DEFAULT 0,
            score_alignment INTEGER NOT NULL DEFAULT 0,
            tags TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Hard-gate tokens for contributor NDA + portal
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contributor_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contributor_id INTEGER NOT NULL,
            purpose TEXT NOT NULL,             -- nda|portal
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (contributor_id) REFERENCES contributors(id)
        )
    """)

    conn.commit()
    conn.close()

init_db()

# --------------------
# Admin guard
# --------------------
def require_admin(request: Request):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set")
    supplied = request.query_params.get("admin_key") or request.headers.get("x-admin-key")
    if supplied != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# --------------------
# Subscriber access helpers
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
# Contributor gating helpers (Hard Gate)
# --------------------
def issue_contributor_token(contributor_id: int, purpose: str, hours: int = 48) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = sha256(token)
    expires = (datetime.utcnow() + timedelta(hours=hours)).isoformat()

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contributor_tokens (contributor_id, purpose, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (contributor_id, purpose, token_hash, expires, now_iso()))
    conn.commit()
    conn.close()
    return token

def validate_contributor_token(token: str, purpose: str) -> int | None:
    token_hash = sha256(token)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT contributor_id, expires_at, used_at
        FROM contributor_tokens
        WHERE token_hash = ? AND purpose = ?
        ORDER BY id DESC
        LIMIT 1
    """, (token_hash, purpose))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None
    if row["used_at"]:
        return None
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires_at:
        return None
    return int(row["contributor_id"])

def mark_contributor_token_used(token: str, purpose: str):
    token_hash = sha256(token)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE contributor_tokens
        SET used_at = ?
        WHERE token_hash = ? AND purpose = ?
    """, (now_iso(), token_hash, purpose))
    conn.commit()
    conn.close()

# --------------------
# Contributor scoring engine (v1)
# --------------------
HIGH_VALUE_ROLES = {
    "LED Wall Manufacturer": 30,
    "LED Wall Supplier": 28,
    "Regional Sales": 26,
    "Distributor": 26,
    "Video Systems / LED Tech": 20,
    "Production Company": 18,
    "Warehouse / Logistics": 18,
    "Rigging": 16,
    "Staging": 16,
    "Audio": 12,
    "Lighting": 12,
    "General": 8,
}

REGION_BOOST_KEYWORDS = {
    "dmv": 18, "washington": 16, "dc": 16, "maryland": 12, "virginia": 12,
    "uae": 18, "dubai": 16, "abudhabi": 16,
    "ny": 10, "new york": 10, "philly": 8, "atl": 8, "la": 8
}

ASSET_KEYWORDS = {
    "led": 18, "wall": 12, "processor": 10, "brompton": 12, "novastar": 12,
    "warehouse": 12, "truck": 10, "trucking": 10, "staging": 10,
    "rigging": 10, "motor": 8, "chain hoist": 8, "flightcase": 6
}

def score_contributor(role: str, assets: str | None, regions: str | None, capacity: str | None, alignment: str | None):
    role_l = (role or "").strip()
    assets_l = (assets or "").lower()
    regions_l = (regions or "").lower()
    capacity_l = (capacity or "").lower()
    alignment_l = (alignment or "").lower()

    score_role = 0
    # best match role weights by "contains"
    for k, v in HIGH_VALUE_ROLES.items():
        if k.lower() in role_l.lower():
            score_role = max(score_role, v)

    score_assets = 0
    for k, v in ASSET_KEYWORDS.items():
        if k in assets_l:
            score_assets += v
    score_assets = min(score_assets, 30)

    score_region = 0
    for k, v in REGION_BOOST_KEYWORDS.items():
        if k in regions_l:
            score_region = max(score_region, v)
    score_region = min(score_region, 20)

    score_capacity = 0
    if any(x in capacity_l for x in ["crew", "teams", "operators", "techs"]):
        score_capacity += 8
    if any(x in capacity_l for x in ["inventory", "stock", "warehouse"]):
        score_capacity += 8
    if any(x in capacity_l for x in ["capital", "financing", "credit", "fund"]):
        score_capacity += 10
    score_capacity = min(score_capacity, 20)

    score_alignment = 0
    if any(x in alignment_l for x in ["stadium", "arena", "event center", "real estate", "venue", "district"]):
        score_alignment += 12
    if any(x in alignment_l for x in ["dmv", "uae", "national", "regional"]):
        score_alignment += 8
    score_alignment = min(score_alignment, 20)

    total = min(100, score_role + score_assets + score_region + score_capacity + score_alignment)

    # tags for filtering
    tags = []
    if "led" in assets_l or "led" in role_l.lower():
        tags.append("led")
    if "dmv" in regions_l or "dc" in regions_l:
        tags.append("dmv")
    if "uae" in regions_l or "dubai" in regions_l:
        tags.append("uae")
    if "warehouse" in assets_l or "warehouse" in capacity_l:
        tags.append("warehouse")
    if "truck" in assets_l or "trucking" in assets_l:
        tags.append("logistics")
    if "rig" in role_l.lower() or "rig" in assets_l:
        tags.append("rigging")

    return total, score_role, score_assets, score_region, score_capacity, score_alignment, ",".join(tags)

# --------------------
# Env checks for Stripe
# --------------------
def require_stripe_env():
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

# --------------------
# Global template vars
# --------------------
def base_ctx(request: Request, **kw):
    ctx = {"request": request, "year": datetime.utcnow().year}
    ctx.update(kw)
    return ctx

# --------------------
# Public Pages
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", base_ctx(request))

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", base_ctx(request))

@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", base_ctx(request))

@app.post("/lead")
async def submit_lead(request: Request):
    data = await request.form()
    form = LeadForm(
        name=str(data.get("name", "")).strip(),
        email=str(data.get("email", "")).strip(),
        phone=str(data.get("phone", "")).strip() or None,
        company=str(data.get("company", "")).strip() or None,
        interest=str(data.get("interest", "")).strip(),
        message=str(data.get("message", "")).strip() or None,
    )

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (name, email, phone, company, interest, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (form.name, form.email, form.phone, form.company, form.interest, form.message, now_iso()))
    conn.commit()
    conn.close()

    # optional notify
    if EMAIL_USER and EMAIL_PASS:
        send_email(EMAIL_USER, "New Lead Intake",
                   f"Name: {form.name}\nEmail: {form.email}\nCompany: {form.company}\nInterest: {form.interest}\nMessage: {form.message}")

    return templates.TemplateResponse("lead_thanks.html", base_ctx(request, name=form.name))

@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", base_ctx(request))

@app.post("/partner")
async def submit_partner(request: Request):
    data = await request.form()
    form = PartnerForm(
        name=str(data.get("name", "")).strip(),
        email=str(data.get("email", "")).strip(),
        company=str(data.get("company", "")).strip(),
        role=str(data.get("role", "")).strip(),
        product_type=str(data.get("product_type", "")).strip(),
        website=str(data.get("website", "")).strip() or None,
        regions=str(data.get("regions", "")).strip() or None,
        message=str(data.get("message", "")).strip() or None,
    )

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, website, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (form.name, form.email, form.company, form.role, form.product_type, form.website, form.regions, form.message, now_iso()))
    conn.commit()
    conn.close()

    if EMAIL_USER and EMAIL_PASS:
        send_email(EMAIL_USER, "New Partner Submission",
                   f"Name: {form.name}\nEmail: {form.email}\nCompany: {form.company}\nRole: {form.role}\nProduct: {form.product_type}\nRegions: {form.regions}\nWebsite: {form.website}\nMessage: {form.message}")

    return templates.TemplateResponse("partner_thanks.html", base_ctx(request, name=form.name))

# --------------------
# Contributor Intake (Hard Gate starts here)
# --------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", base_ctx(request))

@app.post("/contributor")
async def submit_contributor(request: Request):
    data = await request.form()
    form = ContributorForm(
        name=str(data.get("name", "")).strip(),
        email=str(data.get("email", "")).strip(),
        company=str(data.get("company", "")).strip() or None,
        role=str(data.get("role", "")).strip(),
        assets=str(data.get("assets", "")).strip() or None,
        regions=str(data.get("regions", "")).strip() or None,
        capacity=str(data.get("capacity", "")).strip() or None,
        alignment=str(data.get("alignment", "")).strip() or None,
    )

    total, s_role, s_assets, s_region, s_cap, s_align, tags = score_contributor(
        form.role, form.assets, form.regions, form.capacity, form.alignment
    )

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contributors
        (name, email, company, role, assets, regions, capacity, alignment,
         status, nda_accepted_at,
         score_total, score_role_fit, score_assets, score_region, score_capacity, score_alignment, tags,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        form.name, form.email, form.company, form.role, form.assets, form.regions,
        form.capacity, form.alignment,
        total, s_role, s_assets, s_region, s_cap, s_align, tags,
        now_iso(), now_iso()
    ))
    contributor_id = cur.lastrowid
    conn.commit()
    conn.close()

    # notify you
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Contributor Submission (Review Needed)",
            f"ID: {contributor_id}\nName: {form.name}\nEmail: {form.email}\nCompany: {form.company}\nRole: {form.role}\nRegions: {form.regions}\nAssets: {form.assets}\nCapacity: {form.capacity}\nAlignment: {form.alignment}\nScore: {total}\nTags: {tags}"
        )

    return templates.TemplateResponse("contributor_thanks.html", base_ctx(request, name=form.name))

# --------------------
# Subscriber Intake (paid users)
# --------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str | None = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("intake_form.html", base_ctx(request, email=email, token=token))

@app.post("/intake")
async def submit_intake(request: Request, token: str | None = None):
    email, err = require_subscriber_token(token)
    if err:
        return err

    data = await request.form()
    form = IntakeForm(
        name=str(data.get("name", "")).strip(),
        email=str(data.get("email", "")).strip(),
        service_requested=str(data.get("service_requested", "")).strip(),
        notes=str(data.get("notes", "")).strip() or None
    )

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (form.name, form.email, form.service_requested, form.notes, now_iso()))
    conn.commit()
    conn.close()

    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber: {email}\n\nName: {form.name}\nEmail: {form.email}\nService: {form.service_requested}\nNotes: {form.notes}"
        )

    return templates.TemplateResponse("intake_thanks.html", base_ctx(request, email=email, token=token))

# --------------------
# Stripe Checkout
# --------------------
@app.get("/checkout")
def checkout():
    err = require_stripe_env()
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
def success(request: Request, session_id: str | None = None):
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
                    """, (email, str(customer_id), str(subscription_id), now_iso(), now_iso()))
                    conn.commit()
                    conn.close()

                    token = issue_magic_link(email, hours=24)

                    if EMAIL_USER and EMAIL_PASS:
                        app_base = str(request.base_url).rstrip("/")
                        link = f"{app_base}/dashboard?token={token}"
                        send_email(email, "Your Nautical Compass Access Link", f"Your access link (valid 24h):\n{link}\n")
        except Exception as e:
            print("Success Stripe fetch failed:", e)

    return templates.TemplateResponse("success.html", base_ctx(request, token=token, email=email))

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", base_ctx(request))

# --------------------
# Stripe Webhook (keeps subscriber status in sync)
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
# Subscriber Dashboard
# --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str | None = None):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", base_ctx(request, email=email, token=token))

# --------------------
# Contributor HARD GATE FLOW
# Admin -> Send NDA -> Contributor Accept -> Portal
# --------------------
@app.get("/contributor/nda", response_class=HTMLResponse)
def contributor_nda(request: Request, token: str | None = None):
    if not token:
        return HTMLResponse("Missing token.", status_code=401)
    cid = validate_contributor_token(token, purpose="nda")
    if not cid:
        return HTMLResponse("Invalid or expired NDA link.", status_code=401)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM contributors WHERE id = ?", (cid,))
    c = cur.fetchone()
    conn.close()
    if not c:
        return HTMLResponse("Contributor not found.", status_code=404)

    return templates.TemplateResponse("contributor_nda.html", base_ctx(request, c=dict(c), token=token))

@app.post("/contributor/nda/accept")
async def contributor_nda_accept(request: Request):
    data = await request.form()
    token = str(data.get("token") or "").strip()
    if not token:
        return HTMLResponse("Missing token.", status_code=401)

    cid = validate_contributor_token(token, purpose="nda")
    if not cid:
        return HTMLResponse("Invalid or expired NDA link.", status_code=401)

    # mark NDA accepted
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE contributors
        SET status='approved', nda_accepted_at=?, updated_at=?
        WHERE id=?
    """, (now_iso(), now_iso(), cid))
    conn.commit()
    conn.close()

    mark_contributor_token_used(token, purpose="nda")

    # create portal token
    portal_token = issue_contributor_token(cid, purpose="portal", hours=72)

    # optional email
    # (If SMTP configured, we can email the portal link to them)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT email FROM contributors WHERE id=?", (cid,))
    row = cur.fetchone()
    conn.close()
    if row and EMAIL_USER and EMAIL_PASS:
        app_base = str(request.base_url).rstrip("/")
        link = f"{app_base}/contributor/portal?token={portal_token}"
        send_email(row["email"], "Contributor Portal Access", f"Your portal link (valid 72h):\n{link}")

    return RedirectResponse(url=f"/contributor/portal?token={portal_token}", status_code=303)

@app.get("/contributor/portal", response_class=HTMLResponse)
def contributor_portal(request: Request, token: str | None = None):
    if not token:
        return HTMLResponse("Missing token.", status_code=401)

    cid = validate_contributor_token(token, purpose="portal")
    if not cid:
        return HTMLResponse("Invalid or expired portal link.", status_code=401)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM contributors WHERE id=?", (cid,))
    c = cur.fetchone()
    conn.close()
    if not c:
        return HTMLResponse("Contributor not found.", status_code=404)

    if c["status"] != "approved":
        return HTMLResponse("Access not approved.", status_code=403)

    return templates.TemplateResponse("contributor_portal.html", base_ctx(request, c=dict(c)))

# --------------------
# Admin Pages
# --------------------
@app.get("/admin/intake", response_class=HTMLResponse)
def admin_intake(request: Request):
    require_admin(request)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("admin_intake.html", base_ctx(request, rows=rows))

@app.get("/admin/contributors", response_class=HTMLResponse)
def admin_contributors(request: Request, sort: str | None = "score"):
    require_admin(request)
    order = "score_total DESC, id DESC" if (sort or "") == "score" else "id DESC"

    conn = db()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM contributors ORDER BY {order}")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("admin_contributors.html", base_ctx(request, rows=rows, admin_key=ADMIN_KEY))

@app.post("/admin/contributors/{cid}/review")
async def admin_mark_reviewed(request: Request, cid: int):
    require_admin(request)
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status='reviewed', updated_at=? WHERE id=?", (now_iso(), cid))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/admin/contributors?admin_key={ADMIN_KEY}", status_code=303)

@app.post("/admin/contributors/{cid}/send-nda")
async def admin_send_nda(request: Request, cid: int):
    require_admin(request)

    # create NDA token
    nda_token = issue_contributor_token(cid, purpose="nda", hours=72)

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT email, name FROM contributors WHERE id=?", (cid,))
    row = cur.fetchone()
    conn.close()

    app_base = str(request.base_url).rstrip("/")
    nda_link = f"{app_base}/contributor/nda?token={nda_token}"

    # email them if configured
    if row and EMAIL_USER and EMAIL_PASS:
        send_email(
            row["email"],
            "Nautical Compass — NDA Acceptance Required",
            f"Hi {row['name']},\n\nTo proceed, review & accept the NDA here:\n{nda_link}\n\nThis link expires in 72 hours."
        )

    # always show it on the admin screen (even if email isn't configured)
    return RedirectResponse(url=f"/admin/contributors?admin_key={ADMIN_KEY}&nda_link={nda_link}", status_code=303)

@app.get("/admin/roles", response_class=HTMLResponse)
def admin_roles(request: Request):
    require_admin(request)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT role, COUNT(*) as cnt, MAX(score_total) as top
        FROM contributors
        GROUP BY role
        ORDER BY top DESC, cnt DESC
    """)
    roles = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("admin_roles.html", base_ctx(request, roles=roles))

# --------------------
# Dev-only: generate subscriber token without paying (behind DEV_MODE + secret)
# --------------------
@app.get("/dev/generate-token")
def dev_generate_token(email: str, secret: str):
    if DEV_MODE != "1":
        raise HTTPException(status_code=404, detail="Not found")
    if not DEV_TOKEN_SECRET or secret != DEV_TOKEN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Upsert subscriber as active for testing
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO subscribers (email, stripe_customer_id, stripe_subscription_id, status, created_at, updated_at)
        VALUES (?, '', '', 'active', ?, ?)
        ON CONFLICT(email) DO UPDATE SET status='active', updated_at=excluded.updated_at
    """, (email, now_iso(), now_iso()))
    conn.commit()
    conn.close()

    token = issue_magic_link(email, hours=24)
    return {"email": email, "token": token, "dashboard": f"/dashboard?token={token}", "intake": f"/intake-form?token={token}"}

# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
