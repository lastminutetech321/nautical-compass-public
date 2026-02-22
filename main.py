# main.py  (FULL UPDATED SCRIPT — includes THE_VEIL_PORTAL dormant rails)
import os
import json
import uuid
import sqlite3
import smtplib
import hashlib
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, List, Dict, Any

import stripe
from fastapi import FastAPI, Request, HTTPException, Form
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


def _json_dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def _json_loads(s: str, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


# --------------------
# Admin gate (protect admin pages)
# --------------------
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))


def require_admin_key(key: Optional[str]):
    if not ADMIN_KEY:
        # If you didn’t set ADMIN_KEY yet, admin routes are open (your call).
        return
    if _clean(key or "") != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# --------------------
# Stripe Config
# --------------------
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
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

# Optional SMTP override (Mailgun or other)
SMTP_HOST = _clean(os.getenv("SMTP_HOST", "")) or "smtp.gmail.com"
SMTP_PORT = int((_clean(os.getenv("SMTP_PORT", "")) or "465"))
SMTP_USE_STARTTLS = _clean(os.getenv("SMTP_USE_STARTTLS", "false")).lower() in ("1", "true", "yes")


# --------------------
# THE_VEIL_PORTAL (Dormant Rails)
# --------------------
FEATURE_THE_VEIL_PORTAL = "THE_VEIL_PORTAL"
VEIL_MODE = _clean(os.getenv("VEIL_MODE", "false")).lower() in ("1", "true", "yes")
VEIL_KEY = _clean(os.getenv("VEIL_KEY", ""))  # optional key gate
# Secret role name (in-universe only)
ARKITECH_ROLE = "Arkitech"


def veil_guard(request: Request):
    """
    Dormant behavior:
      - If VEIL_MODE=false => 404
      - If VEIL_MODE=true and VEIL_KEY set => require ?k=<VEIL_KEY>
    """
    if not VEIL_MODE:
        raise HTTPException(status_code=404, detail="Not Found")
    if VEIL_KEY:
        k = _clean(request.query_params.get("k", ""))
        if k != VEIL_KEY:
            # show generic 404 to avoid advertising the portal exists
            raise HTTPException(status_code=404, detail="Not Found")


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
    # THE_VEIL_PORTAL tables (dormant rails)
    # --------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS veil_leads (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            email TEXT NOT NULL,
            intent TEXT,
            experience_level TEXT,
            primary_role TEXT,
            track TEXT,

            score_track_frontend INTEGER NOT NULL DEFAULT 0,
            score_backend INTEGER NOT NULL DEFAULT 0,
            score_data INTEGER NOT NULL DEFAULT 0,
            score_devops INTEGER NOT NULL DEFAULT 0,
            score_security INTEGER NOT NULL DEFAULT 0,
            score_product INTEGER NOT NULL DEFAULT 0,

            tools_json TEXT,
            availability_hours_per_week INTEGER,
            pain_points_json TEXT,
            strength_style_json TEXT,
            preference TEXT,

            source TEXT,
            utm_source TEXT,
            utm_medium TEXT,
            utm_campaign TEXT,
            utm_term TEXT,
            utm_content TEXT,
            referrer TEXT,

            status TEXT NOT NULL DEFAULT 'new'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS veil_submissions (
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            created_at TEXT NOT NULL,

            portfolio_links_json TEXT,
            ecosystem_interest_json TEXT,
            comm_preference TEXT,
            contribution_type TEXT,
            nda_ack INTEGER NOT NULL DEFAULT 0,

            challenge_choice TEXT,
            challenge_response TEXT,

            review_status TEXT NOT NULL DEFAULT 'pending',
            review_notes TEXT,

            FOREIGN KEY(lead_id) REFERENCES veil_leads(id)
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

        if SMTP_USE_STARTTLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)


# --------------------
# Contributor scoring + rail assignment
# --------------------
def _score_contributor_track(contribution_track: str, comp_plan: str, assets: str, website: str, company: str, fit_fields: List[str], fit_authority: str) -> int:
    score = 0
    track = (contribution_track or "").strip().lower()

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

    comp = (comp_plan or "").strip().lower()
    if "residual" in comp:
        score += 10
    elif "commission" in comp:
        score += 10
    elif "hourly" in comp:
        score += 6
    elif "equity" in comp or "revshare" in comp:
        score += 8

    if assets and len(assets.strip()) > 10:
        score += 10
    if website and len(website.strip()) > 6:
        score += 6
    if company and len(company.strip()) > 2:
        score += 4

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


def _assign_rail(contribution_track: str, position_interest: str, fit_lane: str, score: int) -> str:
    track = (contribution_track or "").strip().lower()
    pos = (position_interest or "").strip().lower()
    lane = (fit_lane or "").strip().lower()

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
# THE_VEIL_PORTAL scoring
# --------------------
VEIL_TRACKS = ["frontend", "backend", "data", "devops", "security", "product"]


def veil_score_l2(
    tools: List[str],
    availability_bucket: str,
    pain_points: List[str],
    strength_style: List[str],
    preference: str,
) -> Dict[str, int]:
    scores = {t: 0 for t in VEIL_TRACKS}

    # Base weights from preference
    pref = (preference or "").lower()
    if "visual" in pref:
        scores["frontend"] += 2
    if "logic" in pref:
        scores["backend"] += 2
    if "data" in pref:
        scores["data"] += 2
    if "systems" in pref or "deploy" in pref:
        scores["devops"] += 2
    if "security" in pref:
        scores["security"] += 2
    if "product" in pref or "people" in pref:
        scores["product"] += 2

    # Strength style adds
    ss = [s.lower() for s in (strength_style or [])]
    if "communicator" in ss:
        scores["frontend"] += 1
        scores["product"] += 1
    if "builder" in ss or "debugger" in ss:
        scores["backend"] += 1
    if "organizer" in ss:
        scores["product"] += 1
        scores["devops"] += 1
    if "protector" in ss:
        scores["security"] += 1
    if "optimizer" in ss:
        scores["frontend"] += 1
        scores["devops"] += 1

    # Pain points tie-break influence (add points)
    pp = [p.lower() for p in (pain_points or [])]
    if any("design" in p or "ux" in p or "visual" in p for p in pp):
        scores["frontend"] += 2
    if any("bugs" in p or "requirements" in p for p in pp):
        scores["backend"] += 2
    if any("data" in p or "integrity" in p for p in pp):
        scores["data"] += 2
    if any("deployment" in p or "deploy" in p or "cache" in p or "queue" in p for p in pp):
        scores["devops"] += 2
    if any("security" in p for p in pp):
        scores["security"] += 2
    if any("people" in p or "product" in p for p in pp):
        scores["product"] += 2

    # Tools signal
    tl = [t.lower() for t in (tools or [])]
    if "sql" in tl:
        scores["data"] += 1
    if "docker" in tl or "ci/cd" in tl or "linux" in tl or "cloud" in tl:
        scores["devops"] += 1
    if "apis" in tl:
        scores["backend"] += 1
    if "js/ts" in tl:
        scores["frontend"] += 1
    if "python" in tl:
        scores["backend"] += 1

    # Availability bucket => mild multiplier
    ab = (availability_bucket or "").strip()
    if ab == "10+":
        for k in scores:
            scores[k] += 1

    return scores


def veil_pick_track(scores: Dict[str, int], pain_points: List[str]) -> str:
    # Highest score wins, tie-break by pain-points
    best = max(scores.items(), key=lambda kv: kv[1])[0]
    top_score = scores[best]
    tied = [k for k, v in scores.items() if v == top_score]
    if len(tied) == 1:
        return best

    pp = " ".join([p.lower() for p in (pain_points or [])])
    # tie-break preference order based on pain points keywords
    if "security" in pp and "security" in tied:
        return "security"
    if ("deploy" in pp or "deployment" in pp or "systems" in pp) and "devops" in tied:
        return "devops"
    if ("data" in pp or "integrity" in pp) and "data" in tied:
        return "data"
    if ("ux" in pp or "design" in pp or "visual" in pp) and "frontend" in tied:
        return "frontend"
    if ("product" in pp or "people" in pp) and "product" in tied:
        return "product"
    return tied[0]


def veil_map_role(track: str, strength_style: List[str]) -> str:
    ss = [s.lower() for s in (strength_style or [])]
    if track == "frontend":
        return "Cache" if "optimizer" in ss else "Frontend (Fren)"
    if track == "backend":
        return "Backend (Beck)"
    if track == "data":
        return "Logs" if "debugger" in ss else "DB"
    if track == "devops":
        return "Queue" if "organizer" in ss else "Deploy"
    if track == "security":
        return "Envars" if "optimizer" in ss else "Auth"
    if track == "product":
        return "API" if "communicator" in ss else "Domain"
    return "Code"


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
async def lead_submit(
    request: Request,
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
    """, (name, email, phone, company, interest or "", message or "", now_iso()))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "Lead received"})


@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/partner")
async def partner_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    company: str = Form(""),
    role: str = Form(""),
    product_type: str = Form(""),
    website: str = Form(""),
    regions: str = Form(""),
    message: str = Form(""),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, website, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, email, company or "", role or "", product_type or "", website or "", regions or "", message or "", now_iso()))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "Partner submission received"})


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
async def submit_intake(
    request: Request,
    token: str,
    name: str = Form(...),
    email: str = Form(...),
    service_requested: str = Form(...),
    notes: str = Form(""),
):
    auth_email, err = require_subscriber_token(token)
    if err:
        return err

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (name, email, service_requested, notes or "", now_iso()))
    conn.commit()
    conn.close()

    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber: {auth_email}\n\nName: {name}\nEmail: {email}\nService: {service_requested}\nNotes: {notes}"
        )

    return JSONResponse({"status": "Intake stored successfully"})


@app.get("/admin/intake")
def admin_intake_json(limit: int = 50, key: Optional[str] = None):
    require_admin_key(key)
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
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "email": email, "token": token, "year": datetime.utcnow().year},
    )


# --------------------
# Contributor Intake + Admin
# --------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": datetime.utcnow().year})


@app.post("/contributor")
async def submit_contributor(
    request: Request,
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
    # scoring + rail
    fit_fields = [fit_access, fit_build_goal, fit_opportunity, fit_authority, fit_lane, fit_no_conditions, fit_visibility, fit_why_you]
    score = _score_contributor_track(contribution_track, comp_plan, assets, website, company, fit_fields, fit_authority)
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
    rail: Optional[str] = None,
    min_score: Optional[int] = None,
    track: Optional[str] = None,
    key: Optional[str] = None,
):
    require_admin_key(key)
    conn = db()
    cur = conn.cursor()

    query = "SELECT * FROM contributors WHERE 1=1"
    params: List[Any] = []

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
async def update_contributor_status(id: int = Form(...), status: str = Form(...), key: Optional[str] = None):
    require_admin_key(key)
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, id))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})


# --------------------
# Dev Token Route (for testing subscriber-only pages)
# --------------------
DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))


@app.get("/dev/generate-token")
def dev_generate_token(request: Request, email: str, key: str):
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
# THE_VEIL_PORTAL Routes (hidden, not linked)
# --------------------
@app.get("/veil", response_class=HTMLResponse)
def veil_landing(request: Request):
    veil_guard(request)
    return templates.TemplateResponse(
        "veil.html",
        {
            "request": request,
            "year": datetime.utcnow().year,
            "feature": FEATURE_THE_VEIL_PORTAL,
            "arkitech": ARKITECH_ROLE,
            "k": request.query_params.get("k", ""),
        },
    )


@app.get("/arkitech", response_class=HTMLResponse)
def arkitech_alias(request: Request):
    veil_guard(request)
    return veil_landing(request)


@app.get("/veil/check", response_class=HTMLResponse)
def veil_check(request: Request, lead_id: Optional[str] = None, show: Optional[str] = None):
    """
    Level 1 + Level 2 UI (single page).
    Flow:
      - POST L1 -> redirect to /veil/check?lead_id=<id>
      - POST L2 -> redirect to /veil/check?lead_id=<id>&show=passport
    """
    veil_guard(request)

    lead = None
    if lead_id:
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM veil_leads WHERE id = ? LIMIT 1", (lead_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            lead = dict(row)
            lead["tools"] = _json_loads(lead.get("tools_json", ""), [])
            lead["pain_points"] = _json_loads(lead.get("pain_points_json", ""), [])
            lead["strength_style"] = _json_loads(lead.get("strength_style_json", ""), [])

    return templates.TemplateResponse(
        "veil_check.html",
        {
            "request": request,
            "year": datetime.utcnow().year,
            "lead": lead,
            "lead_id": lead_id or "",
            "show": show or "",
            "k": request.query_params.get("k", ""),
        },
    )


@app.post("/veil/intake/l1")
async def veil_intake_l1(
    request: Request,
    email: str = Form(...),
    intent: str = Form("Learn"),
    experience_level: str = Form("New"),
):
    veil_guard(request)

    lead_id = str(uuid.uuid4())
    email = _clean(email).lower()

    # UTM/referrer
    qp = request.query_params
    utm_source = _clean(qp.get("utm_source", ""))
    utm_medium = _clean(qp.get("utm_medium", ""))
    utm_campaign = _clean(qp.get("utm_campaign", ""))
    utm_term = _clean(qp.get("utm_term", ""))
    utm_content = _clean(qp.get("utm_content", ""))
    referrer = _clean(request.headers.get("referer", ""))

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO veil_leads (
            id, created_at, email, intent, experience_level,
            source, utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer,
            status
        )
        VALUES (?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                'new')
    """, (
        lead_id, now_iso(), email, intent, experience_level,
        "veil", utm_source, utm_medium, utm_campaign, utm_term, utm_content, referrer
    ))
    conn.commit()
    conn.close()

    base = str(request.base_url).rstrip("/")
    k = request.query_params.get("k", "")
    kq = f"&k={k}" if k else ""
    return RedirectResponse(f"{base}/veil/check?lead_id={lead_id}{kq}", status_code=303)


@app.post("/veil/intake/l2")
async def veil_intake_l2(
    request: Request,
    lead_id: str = Form(...),
    tools: Optional[List[str]] = Form(None),
    availability: str = Form("0–2"),
    pain_points: Optional[List[str]] = Form(None),
    strength_style: Optional[List[str]] = Form(None),
    preference: str = Form("I like systems"),
):
    veil_guard(request)

    tools = tools or []
    pain_points = pain_points or []
    strength_style = strength_style or []

    # map availability bucket -> hours/week int (rough)
    bucket = availability.strip()
    hours_map = {"0–2": 2, "3–5": 5, "6–10": 10, "10+": 12}
    hours = hours_map.get(bucket, 0)

    scores = veil_score_l2(tools, ("10+" if bucket == "10+" else ""), pain_points, strength_style, preference)
    track = veil_pick_track(scores, pain_points)
    primary_role = veil_map_role(track, strength_style)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE veil_leads
        SET
            primary_role=?,
            track=?,
            score_track_frontend=?,
            score_backend=?,
            score_data=?,
            score_devops=?,
            score_security=?,
            score_product=?,
            tools_json=?,
            availability_hours_per_week=?,
            pain_points_json=?,
            strength_style_json=?,
            preference=?,
            status='routed'
        WHERE id=?
    """, (
        primary_role,
        track,
        int(scores["frontend"]),
        int(scores["backend"]),
        int(scores["data"]),
        int(scores["devops"]),
        int(scores["security"]),
        int(scores["product"]),
        _json_dumps(tools),
        int(hours),
        _json_dumps(pain_points),
        _json_dumps(strength_style),
        preference,
        lead_id
    ))
    conn.commit()
    conn.close()

    base = str(request.base_url).rstrip("/")
    k = request.query_params.get("k", "")
    kq = f"&k={k}" if k else ""
    return RedirectResponse(f"{base}/veil/check?lead_id={lead_id}&show=passport{kq}", status_code=303)


@app.post("/veil/intake/l3")
async def veil_intake_l3(
    request: Request,
    lead_id: str = Form(...),
    portfolio_links: str = Form(""),
    ecosystem_interest: Optional[List[str]] = Form(None),
    comm_preference: str = Form("Email"),
    contribution_type: str = Form(""),
    nda_ack: Optional[str] = Form(None),
    challenge_choice: str = Form(""),
    challenge_response: str = Form(""),
):
    veil_guard(request)

    ecosystem_interest = ecosystem_interest or []
    nda_bool = 1 if (nda_ack or "").lower() in ("1", "true", "yes", "on") else 0

    submission_id = str(uuid.uuid4())
    links = [s.strip() for s in (portfolio_links or "").splitlines() if s.strip()]

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO veil_submissions (
            id, lead_id, created_at,
            portfolio_links_json,
            ecosystem_interest_json,
            comm_preference,
            contribution_type,
            nda_ack,
            challenge_choice,
            challenge_response,
            review_status,
            review_notes
        )
        VALUES (?, ?, ?,
                ?, ?,
                ?, ?,
                ?,
                ?, ?,
                'pending',
                '')
    """, (
        submission_id, lead_id, now_iso(),
        _json_dumps(links),
        _json_dumps(ecosystem_interest),
        comm_preference,
        contribution_type,
        nda_bool,
        challenge_choice,
        challenge_response
    ))
    conn.commit()
    conn.close()

    base = str(request.base_url).rstrip("/")
    k = request.query_params.get("k", "")
    kq = f"&k={k}" if k else ""
    return RedirectResponse(f"{base}/veil/check?lead_id={lead_id}&show=passport{kq}", status_code=303)


# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
