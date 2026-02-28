import os
import sqlite3
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import stripe
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


# ============================================================
# PATHS (LOCKED)
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nc.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


# ============================================================
# APP
# ============================================================
app = FastAPI(title="Nautical Compass Intake")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================
# ENV HELPERS
# ============================================================
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
        raise ValueError(f"{name} must start with http:// or https://")
    return url


# ============================================================
# STRIPE CONFIG
# ============================================================
STRIPE_SECRET_KEY = _clean(os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PRICE_ID = _clean(os.getenv("STRIPE_PRICE_ID", ""))  # subscriber tier
STRIPE_SPONSOR_PRICE_ID = _clean(os.getenv("STRIPE_SPONSOR_PRICE_ID", ""))  # sponsor tier optional
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


# ============================================================
# ADMIN + DEV TOKEN CONFIG
# ============================================================
ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))  # used for admin dashboards
DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))  # secret key for /dev/generate-token


def require_admin(k: Optional[str]) -> None:
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set")
    if not k or _clean(k) != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ============================================================
# EMAIL (OPTIONAL) — kept minimal; do not block deployment
# ============================================================
EMAIL_USER = _clean(os.getenv("EMAIL_USER", ""))
EMAIL_PASS = _clean(os.getenv("EMAIL_PASS", ""))
SMTP_HOST = _clean(os.getenv("SMTP_HOST", ""))  # optional
SMTP_PORT = _clean(os.getenv("SMTP_PORT", ""))  # optional


# ============================================================
# DB
# ============================================================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ============================================================
# TABLES
# ============================================================
def init_db():
    conn = db()
    cur = conn.cursor()

    # Subscribers / magic links
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            status TEXT NOT NULL DEFAULT 'inactive',
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

    # Unified intake engine
    cur.execute("""
        CREATE TABLE IF NOT EXISTS intake_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lane TEXT NOT NULL,                 -- legal | production | labor | partner | lead
            created_at TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            contact_phone TEXT,
            org_name TEXT,
            payload_json TEXT NOT NULL,         -- raw structured answers
            flags_json TEXT NOT NULL,           -- computed risk flags
            route TEXT NOT NULL                 -- where it should go next (ops lane)
        )
    """)

    conn.commit()
    conn.close()

init_db()


# ============================================================
# MAGIC LINKS (SUBSCRIBER ACCESS)
# ============================================================
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


# ============================================================
# RISK FLAGS V1 (RULESET)
# ============================================================
def flag(sev: str, code: str, title: str, meaning: str, action: str) -> Dict[str, str]:
    return {
        "severity": sev,      # low | medium | high
        "code": code,
        "title": title,
        "meaning": meaning,
        "action": action
    }

def risk_flags_legal(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    flags = []
    urgency = (payload.get("urgency") or "").lower()
    timeline = (payload.get("timeline") or "").strip()
    jurisdiction = (payload.get("jurisdiction") or "").strip()
    evidence = (payload.get("evidence") or "").strip()

    if not timeline:
        flags.append(flag("high","NC-L01","Missing timeline",
                          "Without a clear timeline, strategy and deadlines become guesswork.",
                          "Add key dates: event date, notice date, denial date, deadline date."))

    if not jurisdiction:
        flags.append(flag("medium","NC-L02","Jurisdiction not stated",
                          "Court/agency choices depend on jurisdiction.",
                          "Add city/state and where the dispute happened."))

    if len(evidence) < 20:
        flags.append(flag("medium","NC-L03","Evidence thin",
                          "Claims fail when evidence is missing or disorganized.",
                          "List documents: emails, contracts, screenshots, receipts, call logs."))

    if "emergency" in urgency or "today" in urgency:
        flags.append(flag("high","NC-L04","Time pressure",
                          "Urgency increases error risk and reduces options.",
                          "We will prioritize the shortest path: preserve evidence + notice + next action."))

    return flags

def risk_flags_production(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    flags = []
    show_date = (payload.get("show_date") or "").strip()
    load_in = (payload.get("load_in") or "").strip()
    crew_count = int(payload.get("crew_count") or 0)
    venue = (payload.get("venue") or "").strip()
    budget = (payload.get("budget_range") or "").lower()
    gear = (payload.get("gear_needed") or "").strip()
    complexity = (payload.get("complexity") or "").lower()

    if not show_date:
        flags.append(flag("high","AVPT-P01","Show date missing",
                          "Scheduling cannot be confirmed without a show date.",
                          "Add the show date (and time window if possible)."))
    if not load_in:
        flags.append(flag("medium","AVPT-P02","Load-in not defined",
                          "No load-in time leads to late crews and blame cycles.",
                          "Add load-in time, rehearsal time, show time, strike time."))

    if crew_count <= 0:
        flags.append(flag("high","AVPT-P03","Crew count not specified",
                          "We can’t staff accurately without headcount.",
                          "Enter a headcount estimate (you can adjust later)."))
    if crew_count >= 25:
        flags.append(flag("medium","AVPT-P04","Large crew risk",
                          "Large crews require stronger coordination and department leads.",
                          "We will propose department breakdown + chain-of-command."))

    if not venue:
        flags.append(flag("medium","AVPT-P05","Venue unknown",
                          "Venue rules affect rigging, power, docks, labor, and compliance.",
                          "Add venue name + address + loading dock notes."))

    if "low" in budget or "$" in budget and "low" in budget:
        flags.append(flag("medium","AVPT-P06","Budget compression",
                          "Low budget often conflicts with high expectations.",
                          "We’ll confirm scope vs. resources before committing."))

    if len(gear) < 10 and "led" in complexity:
        flags.append(flag("medium","AVPT-P07","LED complexity but gear not specified",
                          "LED builds require exact panel counts, processors, distro, and power plan.",
                          "Specify wall size, resolution goal, processor model, and power constraints."))

    return flags

def risk_flags_labor(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    flags = []
    role = (payload.get("role") or "").lower()
    start = (payload.get("call_time") or "").strip()
    location = (payload.get("location") or "").strip()
    truck = (payload.get("truck_type") or "").lower()
    liftgate = (payload.get("liftgate") or "").lower()
    certs = (payload.get("certs") or "").lower()

    if not start:
        flags.append(flag("high","LMT-W01","Call time missing",
                          "If call time is missing, you risk no-shows and misalignment.",
                          "Add call time + expected duration."))

    if not location:
        flags.append(flag("medium","LMT-W02","Location missing",
                          "Routing and travel pay depend on location.",
                          "Add exact address or venue name."))

    if "driver" in role and not truck:
        flags.append(flag("medium","LMT-W03","Truck type not specified",
                          "Truck size determines what you can accept and what you get paid.",
                          "Choose: Sprinter/Box(12–16)/Box(20–26)/53ft/Other."))

    if "box" in truck and liftgate == "":
        flags.append(flag("low","LMT-W04","Liftgate unknown",
                          "Liftgate affects load speed and safety.",
                          "Confirm liftgate Yes/No."))

    if "fork" in certs and "forklift" not in certs:
        # (soft example)
        pass

    return flags


# ============================================================
# ROUTING (WHERE IT GOES NEXT)
# ============================================================
def route_for_lane(lane: str, payload: Dict[str, Any], flags: List[Dict[str, str]]) -> str:
    # Simple v1 routing; upgrade later to fully automated ops queue
    if lane == "production":
        # If high severity flags exist, route to "ops_review"
        if any(f["severity"] == "high" for f in flags):
            return "avpt_ops_review"
        return "avpt_ready"

    if lane == "labor":
        if any(f["severity"] == "high" for f in flags):
            return "lmt_screening"
        return "lmt_ready"

    if lane == "legal":
        if any(f["severity"] == "high" for f in flags):
            return "nc_priority"
        return "nc_standard"

    return "triage"


# ============================================================
# SAVE INTAKE RECORD
# ============================================================
def save_intake_record(
    lane: str,
    name: str,
    email: str,
    phone: str,
    org_name: str,
    payload: Dict[str, Any],
    flags: List[Dict[str, str]],
    route: str
) -> int:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO intake_records (
            lane, created_at, contact_name, contact_email, contact_phone, org_name,
            payload_json, flags_json, route
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lane, now_iso(), name, email, phone, org_name,
        json.dumps(payload, ensure_ascii=False),
        json.dumps(flags, ensure_ascii=False),
        route
    ))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return int(rid)


# ============================================================
# PAGES (PUBLIC)
# ============================================================
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


# ============================================================
# NC LEGAL INTAKE (SUBSCRIBERS-ONLY)
# ============================================================
@app.get("/intake/legal", response_class=HTMLResponse)
def intake_legal_page(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err
    return templates.TemplateResponse("intake_legal.html", {"request": request, "token": token, "email": email, "year": datetime.utcnow().year})

@app.post("/intake/legal")
def intake_legal_submit(
    token: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    jurisdiction: str = Form(""),
    urgency: str = Form(""),
    timeline: str = Form(""),
    issue: str = Form(""),
    desired_outcome: str = Form(""),
    evidence: str = Form(""),
    notes: str = Form("")
):
    sub_email, err = require_subscriber_token(token)
    if err:
        return err

    payload = {
        "subscriber_email": sub_email,
        "jurisdiction": jurisdiction,
        "urgency": urgency,
        "timeline": timeline,
        "issue": issue,
        "desired_outcome": desired_outcome,
        "evidence": evidence,
        "notes": notes
    }
    flags = risk_flags_legal(payload)
    route = route_for_lane("legal", payload, flags)

    rid = save_intake_record(
        lane="legal",
        name=name,
        email=email,
        phone=phone,
        org_name="",
        payload=payload,
        flags=flags,
        route=route
    )
    return RedirectResponse(f"/results/{rid}", status_code=303)


# ============================================================
# AVPT PRODUCTION COMPANY INTAKE (PUBLIC)
# ============================================================
@app.get("/intake/production", response_class=HTMLResponse)
def intake_production_page(request: Request):
    return templates.TemplateResponse("intake_production.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/intake/production")
def intake_production_submit(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    company: str = Form(""),
    show_name: str = Form(""),
    show_date: str = Form(""),
    venue: str = Form(""),
    load_in: str = Form(""),
    show_time: str = Form(""),
    strike_time: str = Form(""),
    crew_count: str = Form("0"),
    departments: str = Form(""),
    gear_needed: str = Form(""),
    complexity: str = Form(""),
    budget_range: str = Form(""),
    notes: str = Form("")
):
    payload = {
        "company": company,
        "show_name": show_name,
        "show_date": show_date,
        "venue": venue,
        "load_in": load_in,
        "show_time": show_time,
        "strike_time": strike_time,
        "crew_count": crew_count,
        "departments": departments,
        "gear_needed": gear_needed,
        "complexity": complexity,
        "budget_range": budget_range,
        "notes": notes
    }
    flags = risk_flags_production(payload)
    route = route_for_lane("production", payload, flags)

    rid = save_intake_record(
        lane="production",
        name=name,
        email=email,
        phone=phone,
        org_name=company,
        payload=payload,
        flags=flags,
        route=route
    )
    return RedirectResponse(f"/results/{rid}", status_code=303)


# ============================================================
# LMT LABOR/TECH INTAKE (PUBLIC)
# ============================================================
@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor_page(request: Request):
    return templates.TemplateResponse("intake_labor.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/intake/labor")
def intake_labor_submit(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    role: str = Form(""),
    primary_skills: str = Form(""),
    certs: str = Form(""),
    location: str = Form(""),
    call_time: str = Form(""),
    duration: str = Form(""),
    travel_ok: str = Form(""),
    truck_type: str = Form(""),
    liftgate: str = Form(""),
    availability: str = Form(""),
    rate_expectation: str = Form(""),
    notes: str = Form("")
):
    payload = {
        "role": role,
        "primary_skills": primary_skills,
        "certs": certs,
        "location": location,
        "call_time": call_time,
        "duration": duration,
        "travel_ok": travel_ok,
        "truck_type": truck_type,
        "liftgate": liftgate,
        "availability": availability,
        "rate_expectation": rate_expectation,
        "notes": notes
    }
    flags = risk_flags_labor(payload)
    route = route_for_lane("labor", payload, flags)

    rid = save_intake_record(
        lane="labor",
        name=name,
        email=email,
        phone=phone,
        org_name="",
        payload=payload,
        flags=flags,
        route=route
    )
    return RedirectResponse(f"/results/{rid}", status_code=303)


# ============================================================
# RESULTS PAGE (RECEIPT + FLAGS + NEXT STEPS)
# ============================================================
@app.get("/results/{rid}", response_class=HTMLResponse)
def results_page(request: Request, rid: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake_records WHERE id = ? LIMIT 1", (rid,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return HTMLResponse("Result not found.", status_code=404)

    payload = json.loads(row["payload_json"])
    flags = json.loads(row["flags_json"])

    # plain next-step packet v1 (tight and clear)
    lane = row["lane"]
    route = row["route"]

    next_steps = []
    if lane == "production":
        next_steps = [
            "Confirm show date/time + load-in + strike time.",
            "Confirm venue dock/power/rigging constraints.",
            "Lock crew count + departments (A/V, lighting, video, LED, rigging, carpentry).",
            "We’ll route to AVPT Ops for staffing + compliance + execution plan."
        ]
    elif lane == "labor":
        next_steps = [
            "Confirm role + call time + location.",
            "Confirm travel/truck/liftgate (if driving).",
            "We’ll route to LMT screening or ready pool based on risk flags.",
            "You’ll be matched when jobs fit your profile + availability."
        ]
    elif lane == "legal":
        next_steps = [
            "Confirm jurisdiction + timeline.",
            "Organize evidence into a simple list.",
            "We’ll propose the best legal lane: notice/demand/admin remedy/complaint structure.",
            "Your dashboard link is your control center."
        ]
    else:
        next_steps = ["We received your submission and will route it to the correct lane."]

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "row": dict(row),
            "payload": payload,
            "flags": flags,
            "next_steps": next_steps,
            "year": datetime.utcnow().year
        }
    )


# ============================================================
# DASHBOARD (SUBSCRIBER)
# ============================================================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    email, err = require_subscriber_token(token)
    if err:
        return err

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "email": email, "token": token, "year": datetime.utcnow().year}
    )


# ============================================================
# LEAD + PARTNER + SPONSOR (PUBLIC)
# ============================================================
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
    message: str = Form("")
):
    payload = {
        "interest": interest,
        "company": company,
        "message": message
    }
    flags: List[Dict[str, str]] = []
    route = "lead_followup"

    rid = save_intake_record("lead", name, email, phone, company, payload, flags, route)
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
    message: str = Form("")
):
    payload = {
        "company": company,
        "role": role,
        "product_type": product_type,
        "website": website,
        "regions": regions,
        "message": message
    }
    flags: List[Dict[str, str]] = []
    route = "partner_review"

    rid = save_intake_record("partner", name, email, "", company, payload, flags, route)
    return RedirectResponse("/partner/thanks", status_code=303)

@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return templates.TemplateResponse("partner_thanks.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/sponsor", response_class=HTMLResponse)
def sponsor_page(request: Request):
    return templates.TemplateResponse("sponsor.html", {"request": request, "year": datetime.utcnow().year})


# ============================================================
# STRIPE CHECKOUT (SUBSCRIPTION)
# ============================================================
def require_stripe_env_basic():
    if STARTUP_URL_ERROR:
        return JSONResponse({"error": STARTUP_URL_ERROR}, status_code=500)
    missing = []
    if not STRIPE_SECRET_KEY: missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_PRICE_ID: missing.append("STRIPE_PRICE_ID")
    if not SUCCESS_URL: missing.append("SUCCESS_URL")
    if not CANCEL_URL: missing.append("CANCEL_URL")
    if missing:
        return JSONResponse({"error": "Missing environment variables", "missing": missing}, status_code=500)
    return None

@app.get("/checkout")
def checkout():
    err = require_stripe_env_basic()
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

@app.get("/sponsor/checkout")
def sponsor_checkout():
    err = require_stripe_env_basic()
    if err:
        return err
    if not STRIPE_SPONSOR_PRICE_ID:
        return JSONResponse({"error": "STRIPE_SPONSOR_PRICE_ID not set"}, status_code=500)

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_SPONSOR_PRICE_ID, "quantity": 1}],
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
            status = (s.get("status") or "").lower()
            if status in ("complete", "completed"):
                details = s.get("customer_details") or {}
                email = details.get("email")
                customer_id = str(s.get("customer") or "")
                subscription_id = str(s.get("subscription") or "")

                if email:
                    upsert_subscriber_active(email, customer_id, subscription_id)
                    token = issue_magic_link(email, hours=24)
                    base = str(request.base_url).rstrip("/")
                    dashboard_link = f"{base}/dashboard?token={token}"
        except Exception as e:
            print("Success page Stripe fetch failed:", e)

    return templates.TemplateResponse(
        "success.html",
        {"request": request, "token": token, "email": email, "dashboard_link": dashboard_link, "year": datetime.utcnow().year}
    )

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request, "year": datetime.utcnow().year})


# ============================================================
# STRIPE WEBHOOK
# ============================================================
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


# ============================================================
# ADMIN DASHBOARDS (AVPT + LMT + NC)
# ============================================================
@app.get("/admin/intake", response_class=JSONResponse)
def admin_intake_json(limit: int = 50, k: Optional[str] = None):
    require_admin(k)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake_records ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse({"entries": rows})


@app.get("/admin/avpt-dashboard", response_class=HTMLResponse)
def admin_avpt_dashboard(request: Request, k: Optional[str] = None):
    require_admin(k)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake_records WHERE lane='production' ORDER BY id DESC LIMIT 200")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Pre-parse a few fields for display
    for r in rows:
        r["payload"] = json.loads(r["payload_json"])
        r["flags"] = json.loads(r["flags_json"])

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "row": {"lane": "production", "id": "ADMIN_VIEW", "route": "avpt_admin"},
            "payload": {"admin_view": True, "count": len(rows)},
            "flags": [],
            "next_steps": [
                "This is the AVPT admin view. Use /results/{id} for a single record receipt.",
                "Sort is newest-first. Risk flags are computed per record."
            ],
            "year": datetime.utcnow().year
        }
    )


@app.get("/admin/lmt-dashboard", response_class=HTMLResponse)
def admin_lmt_dashboard(request: Request, k: Optional[str] = None):
    require_admin(k)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM intake_records WHERE lane='labor' ORDER BY id DESC LIMIT 200")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "row": {"lane": "labor", "id": "ADMIN_VIEW", "route": "lmt_admin"},
            "payload": {"admin_view": True, "count": len(rows)},
            "flags": [],
            "next_steps": [
                "This is the LMT admin view. Use /results/{id} for a single record receipt.",
                "Next upgrade: add a dedicated HTML table dashboard (we’ll do it after your meeting)."
            ],
            "year": datetime.utcnow().year
        }
    )


# ============================================================
# DEV TOKEN (TEST ACCESS WITHOUT PAYING)
# ============================================================
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
        "legal_intake": f"{base}/intake/legal?token={token}",
    }
