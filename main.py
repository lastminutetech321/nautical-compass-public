import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
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
STRIPE_SECRET_KEY = (os.getenv("STRIPE_SECRET_KEY", "") or "").strip()
STRIPE_PRICE_ID = (os.getenv("STRIPE_PRICE_ID", "") or "").strip()
SUCCESS_URL = (os.getenv("SUCCESS_URL", "") or "").strip()
CANCEL_URL = (os.getenv("CANCEL_URL", "") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET", "") or "").strip()

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

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
    interest: str


class PartnerForm(BaseModel):
    name: str
    email: str
    company: str
    role: str


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
# Database
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
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

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
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()

# --------------------
# Helpers
# --------------------
def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def issue_magic_link(email: str, hours: int = 24) -> str:
    token = secrets.token_urlsafe(32)
    return token


def require_subscriber_token(token: str | None):
    if not token:
        return None, HTMLResponse("Missing token.", status_code=401)
    return "dev@example.com", None


# --------------------
# Public Pages
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request})


# --------------------
# Contributor Routes
# --------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request})


@app.post("/contributor")
def submit_contributor(form: ContributorForm):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contributors (name, email, company, role, assets, regions, capacity, alignment, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        form.name,
        form.email,
        form.company,
        form.role,
        form.assets,
        form.regions,
        form.capacity,
        form.alignment,
        now_iso()
    ))
    conn.commit()
    conn.close()

    return {"status": "Contributor submission received"}


# --------------------
# Dev Token Generator
# --------------------
@app.get("/dev/generate-token")
def dev_generate_token(email: str):
    if os.getenv("DEV_MODE") != "true":
        raise HTTPException(status_code=403, detail="Dev mode disabled")

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO subscribers (email, status, created_at, updated_at)
        VALUES (?, 'active', ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            status='active',
            updated_at=excluded.updated_at
    """, (email, now_iso(), now_iso()))
    conn.commit()
    conn.close()

    token = issue_magic_link(email)

    return {
        "email": email,
        "token": token,
        "intake_url": f"/intake-form?token={token}",
        "dashboard_url": f"/dashboard?token={token}"
    }


# --------------------
# Favicon
# --------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"error": "favicon missing"}, status_code=404) 
