import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
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
app = FastAPI(title="Nautical Compass")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --------------------
# Env
# --------------------
def _clean(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", "").strip()

ADMIN_KEY = _clean(os.getenv("ADMIN_KEY", ""))

DEV_TOKEN_ENABLED = _clean(os.getenv("DEV_TOKEN_ENABLED", "false")).lower() in ("1", "true", "yes")
DEV_TOKEN_KEY = _clean(os.getenv("DEV_TOKEN_KEY", ""))

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

    # Subscribers + magic links (kept minimal here)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
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

    # Production intakes (AVPT client lane)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS production_intakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            city TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            crew_needed TEXT NOT NULL,
            budget_range TEXT NOT NULL,
            scope_clarity TEXT NOT NULL,
            po_ready TEXT NOT NULL,
            coi_required TEXT NOT NULL,
            timeline TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Labor / tech intakes (LMT worker lane)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS labor_intakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            home_city TEXT NOT NULL,
            roles TEXT NOT NULL,
            experience_level TEXT NOT NULL,
            availability_days TEXT NOT NULL,
            has_transport TEXT NOT NULL,
            has_certs TEXT NOT NULL,
            has_llc TEXT NOT NULL,
            has_insurance TEXT NOT NULL,
            rate_min TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Matching v1 tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            production_intake_id INTEGER,
            title TEXT NOT NULL,
            role_needed TEXT NOT NULL,
            city TEXT NOT NULL,
            event_date TEXT NOT NULL,
            call_time TEXT NOT NULL,
            hours_est TEXT NOT NULL,
            rate_offer TEXT NOT NULL,
            liftgate_needed TEXT NOT NULL,
            truck_size TEXT NOT NULL,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            labor_intake_id INTEGER,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            home_city TEXT NOT NULL,
            roles TEXT NOT NULL,
            experience_level TEXT NOT NULL,
            availability_days TEXT NOT NULL,
            has_transport TEXT NOT NULL,
            has_certs TEXT NOT NULL,
            has_llc TEXT NOT NULL,
            has_insurance TEXT NOT NULL,
            rate_min TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'available',
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()

# --------------------
# Auth helpers
# --------------------
def require_admin(k: Optional[str]):
    k = k or ""
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not set")
    if _clean(k) != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Bad admin key")

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

# --------------------
# Risk Flags v1 (RULESET)
# --------------------
def risk_flags_production(p: dict) -> List[dict]:
    flags = []

    def add(code, title, why, severity="MED"):
        flags.append({"code": code, "title": title, "why": why, "severity": severity})

    # Single customer concentration risk (if "one-off / single" style deal)
    if p.get("event_type","").lower() in ("private", "one-off", "one off"):
        add("P001", "Single-customer concentration risk", "One-off deal; margin + scope creep risk higher.", "LOW")

    if p.get("scope_clarity","") in ("Unclear", "Not sure"):
        add("P010", "Scope clarity risk", "Unclear scope increases change orders + blame chain.", "HIGH")

    if p.get("po_ready","") == "No":
        add("P020", "PO / authorization risk", "No PO/authorization increases payment delay risk.", "HIGH")

    if p.get("coi_required","") == "Yes":
        add("P030", "COI compliance requirement", "COI required; must confirm before dispatching.", "MED")

    if p.get("timeline","") in ("Rush (24-48h)", "Emergency (same-day)"):
        add("P040", "Rush timeline risk", "Rush increases cost + staffing failure probability.", "HIGH")

    # Budget sanity
    if "low" in p.get("budget_range","").lower():
        add("P050", "Budget compression risk", "Budget may not support required roles/rates.", "MED")

    return flags

def risk_flags_labor(l: dict) -> List[dict]:
    flags = []

    def add(code, title, why, severity="MED"):
        flags.append({"code": code, "title": title, "why": why, "severity": severity})

    if l.get("has_transport","") == "No":
        add("L010", "Transport reliability risk", "No personal transport; risk of late call-times.", "MED")

    if l.get("has_certs","") == "No":
        add("L020", "Certification / credential risk", "May be blocked from certain venues/roles.", "MED")

    if l.get("has_llc","") == "No":
        add("L030", "Business readiness risk", "No LLC; limits certain commercial pay setups.", "LOW")

    if l.get("has_insurance","") == "No":
        add("L040", "Insurance coverage risk", "No coverage; restricts premium gigs.", "MED")

    # Availability
    if l.get("availability_days","") in ("0-2", "3"):
        add("L050", "Low availability risk", "Limited availability reduces match success.", "LOW")

    return flags

# --------------------
# Basic Match Scoring v1
# --------------------
def score_worker_for_job(worker: dict, job: dict) -> int:
    score = 0
    # Role match
    w_roles = (worker.get("roles") or "").lower()
    needed = (job.get("role_needed") or "").lower()
    if needed and needed in w_roles:
        score += 45
    elif needed:
        score += 5

    # City match
    if (worker.get("home_city") or "").strip().lower() == (job.get("city") or "").strip().lower():
        score += 20
    else:
        score += 8

    # Experience
    exp = (worker.get("experience_level") or "").lower()
    if "lead" in exp or "advanced" in exp:
        score += 12
    elif "intermediate" in exp:
        score += 8
    else:
        score += 4

    # Readiness
    if worker.get("has_transport") == "Yes":
        score += 8
    if worker.get("has_certs") == "Yes":
        score += 6
    if worker.get("has_insurance") == "Yes":
        score += 4

    return int(score)

# --------------------
# Pages (Public)
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.utcnow().year})

# --------------------
# Intake: Production (AVPT client lane)
# --------------------
@app.get("/intake/production", response_class=HTMLResponse)
def intake_production_page(request: Request):
    return templates.TemplateResponse("intake_production.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/intake/production")
def intake_production_submit(
    request: Request,
    company_name: str = Form(...),
    contact_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    city: str = Form(...),
    event_type: str = Form(...),
    event_date: str = Form(...),
    crew_needed: str = Form(...),
    budget_range: str = Form(...),
    scope_clarity: str = Form(...),
    po_ready: str = Form(...),
    coi_required: str = Form(...),
    timeline: str = Form(...),
    notes: str = Form(""),
):
    payload = dict(
        company_name=company_name,
        contact_name=contact_name,
        email=email,
        phone=phone,
        city=city,
        event_type=event_type,
        event_date=event_date,
        crew_needed=crew_needed,
        budget_range=budget_range,
        scope_clarity=scope_clarity,
        po_ready=po_ready,
        coi_required=coi_required,
        timeline=timeline,
        notes=notes,
        created_at=now_iso(),
    )
    flags = risk_flags_production(payload)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO production_intakes (
            company_name, contact_name, email, phone, city, event_type, event_date, crew_needed,
            budget_range, scope_clarity, po_ready, coi_required, timeline, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_name, contact_name, email, phone, city, event_type, event_date, crew_needed,
        budget_range, scope_clarity, po_ready, coi_required, timeline, notes, payload["created_at"]
    ))
    pid = cur.lastrowid
    conn.commit()
    conn.close()

    # Store flags in session-less way: render results from computed flags (no persistence needed for v1)
    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "year": datetime.utcnow().year,
            "lane": "production",
            "record_id": pid,
            "headline": "Production Intake Received",
            "subhead": "We extracted operational risks + routing signals.",
            "flags": flags,
            "next_actions": [
                {"label": "Open Production Dashboard", "href": f"/dash/production?id={pid}"},
                {"label": "Create a Job Request (Matching v1)", "href": f"/dash/production?id={pid}#jobs"},
                {"label": "View Services", "href": "/services"},
            ],
        },
    )

# --------------------
# Intake: Labor/Tech (LMT worker lane)
# --------------------
@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor_page(request: Request):
    return templates.TemplateResponse("intake_labor.html", {"request": request, "year": datetime.utcnow().year})

@app.post("/intake/labor")
def intake_labor_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    home_city: str = Form(...),
    roles: str = Form(...),
    experience_level: str = Form(...),
    availability_days: str = Form(...),
    has_transport: str = Form(...),
    has_certs: str = Form(...),
    has_llc: str = Form(...),
    has_insurance: str = Form(...),
    rate_min: str = Form(...),
    notes: str = Form(""),
):
    payload = dict(
        name=name,
        email=email,
        phone=phone,
        home_city=home_city,
        roles=roles,
        experience_level=experience_level,
        availability_days=availability_days,
        has_transport=has_transport,
        has_certs=has_certs,
        has_llc=has_llc,
        has_insurance=has_insurance,
        rate_min=rate_min,
        notes=notes,
        created_at=now_iso(),
    )
    flags = risk_flags_labor(payload)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO labor_intakes (
            name, email, phone, home_city, roles, experience_level, availability_days,
            has_transport, has_certs, has_llc, has_insurance, rate_min, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name, email, phone, home_city, roles, experience_level, availability_days,
        has_transport, has_certs, has_llc, has_insurance, rate_min, notes, payload["created_at"]
    ))
    lid = cur.lastrowid

    # Upsert worker into workers table (so matching works immediately)
    cur.execute("""
        INSERT INTO workers (
            labor_intake_id, name, email, phone, home_city, roles, experience_level,
            availability_days, has_transport, has_certs, has_llc, has_insurance, rate_min, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?)
    """, (
        lid, name, email, phone, home_city, roles, experience_level,
        availability_days, has_transport, has_certs, has_llc, has_insurance, rate_min, payload["created_at"]
    ))

    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "year": datetime.utcnow().year,
            "lane": "labor",
            "record_id": lid,
            "headline": "Labor / Tech Intake Received",
            "subhead": "We extracted readiness risks + match signals.",
            "flags": flags,
            "next_actions": [
                {"label": "Open Labor Dashboard", "href": f"/dash/labor?id={lid}"},
                {"label": "View Services", "href": "/services"},
                {"label": "Join Contributor Track", "href": "/contributor"},
            ],
        },
    )

# --------------------
# Dashboards
# --------------------
@app.get("/dash/production", response_class=HTMLResponse)
def dash_production(request: Request, id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM production_intakes WHERE id = ? LIMIT 1", (id,))
    prod = cur.fetchone()
    if not prod:
        conn.close()
        raise HTTPException(status_code=404, detail="Production intake not found")

    cur.execute("SELECT * FROM jobs WHERE production_intake_id = ? ORDER BY id DESC", (id,))
    jobs = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "dash_production.html",
        {"request": request, "year": datetime.utcnow().year, "prod": dict(prod), "jobs": jobs},
    )

@app.post("/dash/production/create-job")
def create_job(
    production_intake_id: int = Form(...),
    title: str = Form(...),
    role_needed: str = Form(...),
    city: str = Form(...),
    event_date: str = Form(...),
    call_time: str = Form(...),
    hours_est: str = Form(...),
    rate_offer: str = Form(...),
    truck_size: str = Form(...),
    liftgate_needed: str = Form(...),
    notes: str = Form(""),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO jobs (
            production_intake_id, title, role_needed, city, event_date, call_time,
            hours_est, rate_offer, liftgate_needed, truck_size, notes, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
    """, (
        production_intake_id, title, role_needed, city, event_date, call_time,
        hours_est, rate_offer, liftgate_needed, truck_size, notes, now_iso()
    ))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/dash/production?id={production_intake_id}#jobs", status_code=303)

@app.get("/dash/labor", response_class=HTMLResponse)
def dash_labor(request: Request, id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM labor_intakes WHERE id = ? LIMIT 1", (id,))
    labor = cur.fetchone()
    if not labor:
        conn.close()
        raise HTTPException(status_code=404, detail="Labor intake not found")

    # show recent open jobs (for the worker to browse)
    cur.execute("SELECT * FROM jobs WHERE status='open' ORDER BY id DESC LIMIT 25")
    jobs = [dict(r) for r in cur.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "dash_labor.html",
        {"request": request, "year": datetime.utcnow().year, "labor": dict(labor), "jobs": jobs},
    )

# --------------------
# Matching v1
# --------------------
@app.get("/matching/run")
def run_matching(job_id: int):
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM jobs WHERE id = ? LIMIT 1", (job_id,))
    job = cur.fetchone()
    if not job:
        conn.close()
        return JSONResponse({"error": "Job not found"}, status_code=404)

    cur.execute("SELECT * FROM workers WHERE status='available' ORDER BY id DESC LIMIT 200")
    workers = [dict(r) for r in cur.fetchall()]
    conn.close()

    scored = []
    for w in workers:
        s = score_worker_for_job(w, dict(job))
        scored.append({"score": s, "worker": w})

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:25]

    return {"job": dict(job), "matches": top}

# --------------------
# Contributor (kept as existing public form route)
# --------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    # If you already have contributor_intake.html, keep it.
    # If not, create it later — this route is here so your nav doesn't dead-end.
    file_path = TEMPLATES_DIR / "contributor_intake.html"
    if file_path.exists():
        return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": datetime.utcnow().year})
    return HTMLResponse(
        "<h2>Contributor Intake (Coming Online)</h2><p>This lane is ready; template will be added next.</p>",
        status_code=200
    )

# --------------------
# Admin dashboards (do not expose publicly; requires k=ADMIN_KEY)
# --------------------
@app.get("/admin/leads-dashboard", response_class=HTMLResponse)
def admin_leads_dashboard(request: Request, k: Optional[str] = None):
    require_admin(k)
    # Minimal placeholder so button doesn't dead-end.
    return HTMLResponse("<h2>Leads Dashboard</h2><p>Wired. (We’ll render leads table next.)</p>")

# --------------------
# Dev token route (so you can test access without paying)
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

    token = issue_magic_link(email, hours=24)
    base = str(request.base_url).rstrip("/")
    return {
        "email": email,
        "token": token,
        "dashboard": f"{base}/dashboard?token={token}",
        "production_intake": f"{base}/intake/production",
        "labor_intake": f"{base}/intake/labor",
    }

# --------------------
# Subscriber dashboard (placeholder, so token links never dead-end)
# --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def subscriber_dashboard(request: Request, token: str):
    email = validate_magic_link(token)
    if not email:
        return HTMLResponse("Invalid or expired link.", status_code=401)

    # This is your NC subscriber lane placeholder.
    # We keep it simple and wired.
    return HTMLResponse(
        f"<h2>Subscriber Dashboard</h2><p>Authorized: <b>{email}</b></p>"
        f"<p><a href='/services'>Services</a> · <a href='/intake/production'>Production Intake</a> · <a href='/intake/labor'>Labor Intake</a></p>",
        status_code=200
    )

# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon.ico missing in /static"}, status_code=404)
