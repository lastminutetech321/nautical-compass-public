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
# Env helpers (FIXES your Stripe URL + key corruption issues)
# --------------------
def _clean_env(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\r", "").replace("\n", "")
    # common user copy/paste poison:
    if s.lower().startswith("value:"):
        s = s.split(":", 1)[1].strip()
    # remove wrapping quotes if present
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s

def _clean_url(s: str) -> str:
    s = _clean_env(s)
    # Stripe requires absolute URL with scheme
    # (we won't auto-add https because you WANT correctness)
    return s

# --------------------
# Stripe Config
# --------------------
STRIPE_SECRET_KEY = _clean_env(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean_env(os.getenv("STRIPE_PRICE_ID", ""))
SUCCESS_URL = _clean_url(os.getenv("SUCCESS_URL", ""))
CANCEL_URL = _clean_url(os.getenv("CANCEL_URL", ""))
STRIPE_WEBHOOK_SECRET = _clean_env(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# --------------------
# Email (optional)
# --------------------
# (leave empty until you finish Mailgun/Gmail app password)
EMAIL_USER = _clean_env(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean_env(os.getenv("EMAIL_PASS", ""))

# Dev token gate (optional)
DEV_TOKEN_KEY = _clean_env(os.getenv("DEV_TOKEN_KEY", ""))  # set this if you want /dev/generate-token enabled

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
            interest TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            role TEXT,
            product_type TEXT,
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

    conn.commit()
    conn.close()

init_db()

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
# Magic link + subscriber gate
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
# Config validation (STOP Stripe URL errors permanently)
# --------------------
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

    # Validate URLs for Stripe
    bad_urls = []
    if SUCCESS_URL and not (SUCCESS_URL.startswith("https://") or SUCCESS_URL.startswith("http://")):
        bad_urls.append({"SUCCESS_URL": SUCCESS_URL})
    if CANCEL_URL and not (CANCEL_URL.startswith("https://") or CANCEL_URL.startswith("http://")):
        bad_urls.append({"CANCEL_URL": CANCEL_URL})

    if missing or bad_urls:
        return JSONResponse(
            {"error": "Missing or invalid environment variables", "missing": missing, "bad_urls": bad_urls},
            status_code=500
        )
    return None

# --------------------
# Public Pages
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request})

@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request})

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
    return {"status": "Lead received"}

@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request})

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
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (name, email, company, role, product_type, website, regions, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, email, company, role, product_type, website, regions, message, now_iso()))
    conn.commit()
    conn.close()
    return {"status": "Partner submission received"}

# --------------------
# Subscriber Intake (token protected)
# --------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("intake_form.html", {"request": request, "email": email, "token": token})

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

    return {"status": "Intake stored successfully"}

@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake ORDER BY id DESC LIMIT ?", (int(limit),))
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
def success(request: Request, session_id: str | None = None):
    token = None
    email = None

    # We try to generate access on the success page too (so email can be optional)
    if session_id and STRIPE_SECRET_KEY:
        try:
            s = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])
            # Stripe session status typically "complete"
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
                        send_email(email, "Your Nautical Compass Access Link", f"Access link (24h):\n{link}\n")
        except Exception as e:
            print("Success page Stripe fetch failed:", e)

    return templates.TemplateResponse("success.html", {"request": request, "token": token, "email": email})

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request})

# --------------------
# Stripe Webhook (GRANTS ACCESS)
# IMPORTANT: we support BOTH paths so your Stripe endpoint can be either one.
# --------------------
@app.post("/webhook/stripe")
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
        customer_email = (session.get("customer_details") or {}).get("email")
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

            token = issue_magic_link(customer_email, hours=24)
            app_base = str(request.base_url).rstrip("/")
            link = f"{app_base}/dashboard?token={token}"

            if EMAIL_USER and EMAIL_PASS:
                send_email(customer_email, "Your Nautical Compass Access Link", f"Access link (24h):\n{link}\n")

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
# Dashboard (Magic Link Protected)
# --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("dashboard.html", {"request": request, "email": email, "token": token})

# --------------------
# Contributor Intake + Scoring + Admin Dashboard
# --------------------
def _score_contributor(contribution_track: str, comp_plan: str, assets: str, website: str, company: str,
                      fit_access: str, fit_build_goal: str, fit_opportunity: str, fit_authority: str,
                      fit_lane: str, fit_no_conditions: str, fit_visibility: str, fit_why_you: str) -> int:
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

def _assign_rail(contribution_track: str, position_interest: str, fit_lane: str, score: int) -> str:
    track = (contribution_track or "").strip().lower()
    pos = (position_interest or "").strip().lower()
    lane = (fit_lane or "").strip().lower()

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

@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request})

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
    score = _score_contributor(contribution_track, comp_plan, assets, website, company,
                              fit_access, fit_build_goal, fit_opportunity, fit_authority,
                              fit_lane, fit_no_conditions, fit_visibility, fit_why_you)
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
):
    conn = db()
    cur = conn.cursor()

    query = "SELECT * FROM contributors WHERE 1=1"
    params = []

    if rail:
        query += " AND rail = ?"
        params.append(rail)

    if min_score is not None:
        query += " AND score >= ?"
        params.append(int(min_score))

    if track:
        query += " AND contribution_track = ?"
        params.append(track)

    query += " ORDER BY score DESC"

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "contributors_dashboard.html",
        {"request": request, "contributors": rows, "rail": rail, "min_score": min_score, "track": track},
    )

@app.post("/admin/contributor-status")
def update_contributor_status(id: int = Form(...), status: str = Form(...)):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, int(id)))
    conn.commit()
    conn.close()
    return {"ok": True}

# --------------------
# Dev-only token generator
# Usage:
#   /dev/generate-token?email=youremail@example.com&key=DEV_TOKEN_KEY
# --------------------
@app.get("/dev/generate-token")
def dev_generate_token(email: str, key: str):
    if not DEV_TOKEN_KEY:
        return JSONResponse({"error": "DEV_TOKEN_KEY not set"}, status_code=403)
    if key != DEV_TOKEN_KEY:
        return JSONResponse({"error": "Bad key"}, status_code=403)

    # ensure subscriber row exists + active (dev convenience)
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
    app_base = ""  # we will just return token; you can paste into /dashboard
    return {"token": token, "dashboard": f"/dashboard?token={token}", "intake": f"/intake-form?token={token}"}

# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
