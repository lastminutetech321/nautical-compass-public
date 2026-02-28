import os
import sqlite3
import smtplib
import hashlib
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Dict, Any, List

import stripe
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


# =========================
# PATHS (LOCKED)
# =========================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nc.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


# =========================
# APP
# =========================
app = FastAPI(title="Nautical Compass Intake", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =========================
# CLEAN / ENV HELPERS
# =========================
def _clean(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", "").strip()

def _clean_url(s: str) -> str:
    s = _clean(s)
    # Protect against user accidentally pasting "Value: https://..."
    if s.lower().startswith("value:"):
        s = s.split(":", 1)[1].strip()
    return s

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# =========================
# STRIPE CONFIG
# =========================
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))
STRIPE_WEBHOOK_SECRET = _clean(os.getenv("STRIPE_WEBHOOK_SECRET", ""))

SUCCESS_URL = _clean_url(os.getenv("SUCCESS_URL", ""))
CANCEL_URL = _clean_url(os.getenv("CANCEL_URL", ""))

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


# =========================
# EMAIL (OPTIONAL)
# =========================
# NOTE: Keep these if you want notifications. If not set, app still works.
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))


# =========================
# ADMIN + DEV TOKEN
# =========================
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))


def require_admin(k: Optional[str], key: Optional[str]):
    supplied = _clean(k or "") or _clean(key or "")
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured in environment variables.")
    if not supplied or supplied != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized (bad admin key).")


# =========================
# DB
# =========================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    # Subscriber intake
    cur.execute("""
        CREATE TABLE IF NOT EXISTS intake (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_email TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            service_requested TEXT NOT NULL,
            notes TEXT,
            facts_json TEXT,
            flags_json TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Leads (public)
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

    # Partners (manufacturers/vendors)
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

    conn.commit()
    conn.close()


init_db()


# =========================
# EMAIL SENDER
# =========================
def send_email(to_email: str, subject: str, body: str):
    if not (EMAIL_USER and EMAIL_PASS):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg.set_content(body)

        # Default Gmail SMTP_SSL. If you later use Mailgun SMTP, switch host/port.
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
    except Exception as e:
        print("Email failed:", e)


# =========================
# MAGIC LINKS
# =========================
def issue_magic_link(email: str, hours: int = 24) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = sha256(token)
    expires = (datetime.utcnow() + timedelta(hours=hours)).isoformat()

    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO magic_links (email, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (email.lower(), token_hash, expires, now_iso())
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
    cur.execute("SELECT status FROM subscribers WHERE email = ? LIMIT 1", (email.lower(),))
    row = cur.fetchone()
    conn.close()
    return bool(row) and row["status"] == "active"


def upsert_subscriber_active(email: str, customer_id: str = "", subscription_id: str = ""):
    email = (email or "").lower().strip()
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


# =========================
# LEGAL SPINE v1 (CURATED)
# Dual-mode: Basic + Court-Ready
# =========================
LEGAL_SPINE: Dict[str, Dict[str, Any]] = {
    "standing_article_iii": {
        "title": "Article III Standing (Federal Court)",
        "basic": [
            "To be heard in federal court, you generally must show: (1) real harm, (2) it was caused by the defendant, and (3) the court can fix it.",
        ],
        "court_ready": [
            {
                "rule": "Plaintiff must establish (1) injury in fact, (2) causation, and (3) redressability.",
                "cite": "Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992)."
            },
            {
                "rule": "A statutory violation alone may be insufficient without concrete harm.",
                "cite": "Spokeo, Inc. v. Robins, 578 U.S. 330 (2016); TransUnion LLC v. Ramirez, 594 U.S. 413 (2021)."
            },
        ],
        "facts_needed": [
            "What exactly happened (dates, actors, location)",
            "What harm occurred (financial loss, denial of service, reputational harm, loss of opportunity, etc.)",
            "How defendant’s act caused it (the link)",
            "What remedy you want (money, injunction, correction, access, stop conduct)",
        ],
    },
    "capacity_official_individual": {
        "title": "Individual vs Official Capacity (Suing Officials)",
        "basic": [
            "If you sue an official personally, you seek damages from them. If you sue officially, you usually seek policy change or injunctions.",
        ],
        "court_ready": [
            {
                "rule": "Official-capacity suits are treated as suits against the governmental entity; individual-capacity targets the person.",
                "cite": "Kentucky v. Graham, 473 U.S. 159 (1985)."
            },
            {
                "rule": "State officials can be sued for prospective injunctive relief to stop ongoing violations (Ex parte Young).",
                "cite": "Ex parte Young, 209 U.S. 123 (1908)."
            },
            {
                "rule": "State officials can be liable in personal capacity for constitutional violations under § 1983.",
                "cite": "Hafer v. Melo, 502 U.S. 21 (1991)."
            },
        ],
        "facts_needed": [
            "Who did what (specific official actions)",
            "Whether harm is ongoing (for injunction)",
            "Whether you want damages vs prospective relief",
        ],
    },
}

# =========================
# RISK FLAGS v1 (RULESET)
# =========================
def risk_flags_v1(intake: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Returns list of flags: {code, title, severity, why, fix}
    """
    flags: List[Dict[str, str]] = []

    service = (intake.get("service_requested") or "").lower().strip()
    notes = (intake.get("notes") or "").strip()

    # Universal: thin facts
    if len(notes) < 40:
        flags.append({
            "code": "RF_FACTS_THIN",
            "title": "Thin facts",
            "severity": "medium",
            "why": "Not enough factual detail to triage quickly or map standing/capacity.",
            "fix": "Add timeline: what happened, when, who, where, harm, what you want."
        })

    # Standing: needs concrete injury + remedy clarity
    wants = intake.get("wants") or ""
    if not wants:
        flags.append({
            "code": "RF_REMEDY_UNCLEAR",
            "title": "Requested relief unclear",
            "severity": "medium",
            "why": "Redressability depends on what the court/decision-maker can actually order.",
            "fix": "Specify: damages amount, correction, injunction/stop conduct, record release, etc."
        })

    injury = intake.get("injury") or ""
    if not injury:
        flags.append({
            "code": "RF_INJURY_UNSTATED",
            "title": "Injury not stated",
            "severity": "high",
            "why": "Standing typically fails without a concrete injury (harm).",
            "fix": "State your harm: money, denial, lost work, time, privacy invasion, reputational harm, etc."
        })

    # Contract review: missing contract upload mention
    if "contract" in service and ("contract" not in notes.lower()):
        flags.append({
            "code": "RF_DOC_MISSING_CONTRACT",
            "title": "Contract not referenced",
            "severity": "low",
            "why": "Contract review requires the document or key clauses.",
            "fix": "Attach or paste relevant clauses, parties, dates, payment terms, termination, liability."
        })

    # Arbitration: missing forum/contract clause
    if "arbitration" in service and ("arbitration" not in notes.lower()):
        flags.append({
            "code": "RF_ARB_FORUM_UNKNOWN",
            "title": "Arbitration clause/forum unknown",
            "severity": "medium",
            "why": "Package depends on clause, provider (AAA/JAMS), deadlines, and notice requirements.",
            "fix": "Provide clause text or where it appears; note any deadlines or prior notices."
        })

    # Evidence organization: missing exhibits mention
    if "evidence" in service and ("photo" not in notes.lower() and "email" not in notes.lower() and "text" not in notes.lower()):
        flags.append({
            "code": "RF_EVIDENCE_UNLISTED",
            "title": "Evidence not listed",
            "severity": "low",
            "why": "We can’t map exhibits to claims without knowing what exists.",
            "fix": "List what you have: screenshots, emails, invoices, contracts, recordings, witnesses."
        })

    return flags


def spine_pick(service_requested: str) -> List[str]:
    """
    Decide which spine topics to show based on service.
    """
    s = (service_requested or "").lower()
    topics = ["standing_article_iii"]  # default anchor
    if any(x in s for x in ["official", "1983", "civil rights", "injunction", "government"]):
        topics.append("capacity_official_individual")
    return topics


# =========================
# ENV REQUIREMENTS (STRIPE)
# =========================
def require_stripe_env():
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
        return JSONResponse({"error": "Missing/invalid environment variables", "missing": missing}, status_code=500)
    return None


# =========================
# CORE PAGES
# =========================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)


# =========================
# PUBLIC LEAD + PARTNER
# =========================
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


# =========================
# STRIPE CHECKOUT
# =========================
@app.get("/checkout")
def checkout(ref: Optional[str] = None):
    err = require_stripe_env()
    if err:
        return err

    try:
        # Store ref if you want later attribution (can be expanded).
        # For now we keep it simple.
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

    # If Stripe returns session_id, we try to grant access.
    if session_id and STRIPE_SECRET_KEY:
        try:
            s = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])
            details = s.get("customer_details") or {}
            email = (details.get("email") or "").strip().lower()

            customer_id = str(s.get("customer") or "")
            subscription_id = str(s.get("subscription") or "")

            if email:
                upsert_subscriber_active(email, customer_id, subscription_id)
                token = issue_magic_link(email, hours=24)
                base = str(request.base_url).rstrip("/")
                dashboard_link = f"{base}/dashboard?token={token}"

                # Email if configured
                if EMAIL_USER and EMAIL_PASS:
                    send_email(
                        email,
                        "Your Nautical Compass Access Link",
                        f"Welcome.\n\nYour access link (valid 24 hours):\n{dashboard_link}\n"
                    )

        except Exception as e:
            print("Success fetch failed:", e)

    return templates.TemplateResponse(
        "success.html",
        {"request": request, "token": token, "email": email, "dashboard_link": dashboard_link, "year": datetime.utcnow().year},
    )


@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request, "year": datetime.utcnow().year})


# =========================
# STRIPE WEBHOOK (PROD)
# =========================
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

    # Payment completed
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = str(session.get("customer") or "")
        customer_email = (session.get("customer_details", {}) or {}).get("email")
        subscription_id = str(session.get("subscription") or "")

        if customer_email:
            customer_email = customer_email.strip().lower()
            upsert_subscriber_active(customer_email, customer_id, subscription_id)

            # Email access link if configured
            token = issue_magic_link(customer_email, hours=24)
            base = str(request.base_url).rstrip("/")
            link = f"{base}/dashboard?token={token}"

            if EMAIL_USER and EMAIL_PASS:
                send_email(
                    customer_email,
                    "Your Nautical Compass Access Link",
                    f"Welcome.\n\nYour access link (valid 24 hours):\n{link}\n"
                )

    # Subscription canceled
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


# Compatibility alias (some dashboards show /webhook/stripe)
@app.post("/webhook/stripe")
async def stripe_webhook_alias(request: Request):
    return await stripe_webhook(request)


# =========================
# SUBSCRIBER DASH + INTAKE
# =========================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "email": email, "token": token, "year": datetime.utcnow().year},
    )


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
def submit_intake(
    token: str,
    name: str = Form(...),
    email: str = Form(...),
    service_requested: str = Form(...),
    notes: str = Form(""),
    # Minimal “facts” used for Risk Flags + Standing logic:
    injury: str = Form(""),
    wants: str = Form(""),
    defendant_type: str = Form(""),   # gov / company / person / unknown
    timeline: str = Form(""),         # dates summary
):
    subscriber_email, err = require_subscriber_token(token)
    if err:
        return err

    intake_obj = {
        "subscriber_email": subscriber_email,
        "name": name,
        "email": email,
        "service_requested": service_requested,
        "notes": notes or "",
        "injury": injury or "",
        "wants": wants or "",
        "defendant_type": defendant_type or "",
        "timeline": timeline or "",
    }

    flags = risk_flags_v1(intake_obj)
    topics = spine_pick(service_requested)

    # Store in DB
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake (subscriber_email, name, email, service_requested, notes, facts_json, flags_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        subscriber_email,
        name,
        email,
        service_requested,
        notes or "",
        str(intake_obj),
        str(flags),
        now_iso(),
    ))
    intake_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Optional internal notification
    if EMAIL_USER and EMAIL_PASS:
        send_email(
            EMAIL_USER,
            "New Subscriber Intake Submission",
            f"Subscriber: {subscriber_email}\n\n"
            f"Name: {name}\nEmail: {email}\nService: {service_requested}\n\n"
            f"Injury: {injury}\nWants: {wants}\nDefendant type: {defendant_type}\nTimeline: {timeline}\n\n"
            f"Notes:\n{notes}\n"
        )

    # Redirect to Results (dual mode supported via ?mode=basic or ?mode=court)
    return RedirectResponse(f"/results?id={intake_id}&token={token}&mode=basic", status_code=303)


# =========================
# RESULTS ROUTE (RISK FLAGS + LEGAL SPINE)
# =========================
@app.get("/results", response_class=HTMLResponse)
def results(request: Request, id: int, token: str, mode: str = "basic"):
    """
    mode:
      - basic: plain-language
      - court: court-ready citations + element checklist
    """
    subscriber_email, err = require_subscriber_token(token)
    if err:
        return err

    # Fetch intake
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake WHERE id = ? LIMIT 1", (id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return HTMLResponse("Intake not found.", status_code=404)

    # Ensure subscriber is viewing their own intake (basic isolation)
    if row["subscriber_email"] != subscriber_email:
        return HTMLResponse("Unauthorized.", status_code=403)

    intake_obj = row["facts_json"] or ""
    # re-run flags (don’t trust stale strings)
    flags = risk_flags_v1({
        "service_requested": row["service_requested"],
        "notes": row["notes"] or "",
        "injury": "",  # stored inside facts_json string — we treat it as optional for now
        "wants": "",
    })

    topics = spine_pick(row["service_requested"])
    spine_blocks = []
    for t in topics:
        entry = LEGAL_SPINE.get(t)
        if entry:
            spine_blocks.append(entry)

    mode = (mode or "basic").lower().strip()
    if mode not in ("basic", "court"):
        mode = "basic"

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "token": token,
            "mode": mode,
            "intake_id": row["id"],
            "service_requested": row["service_requested"],
            "notes": row["notes"] or "",
            "flags": flags,
            "spine": spine_blocks,
            "year": datetime.utcnow().year,
        },
    )


# =========================
# ADMIN (JSON intake + Leads dashboard)
# =========================
@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id, subscriber_email, name, email, service_requested, created_at FROM intake ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}


@app.get("/admin/leads-dashboard", response_class=HTMLResponse)
def leads_dashboard(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    require_admin(k, key)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse(
        "leads_dashboard.html",
        {"request": request, "leads": rows, "k": _clean(k or key or ""), "year": datetime.utcnow().year},
    )


# =========================
# DEV TOKEN ROUTE (TEST ACCESS)
# =========================
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
