import os
import hmac
import json
import time
import base64
import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Stripe is optional at runtime (keeps app booting even if env not set yet)
try:
    import stripe  # type: ignore
except Exception:
    stripe = None


# ------------------------------------------------------------
# App + Templates + Static
# ------------------------------------------------------------

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------

APP_ENV = os.getenv("APP_ENV", "prod").lower().strip()
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")  # optional; used for absolute links
DB_PATH = os.getenv("DB_PATH", "nc.db")

TOKEN_SECRET = os.getenv("TOKEN_SECRET", "change-me-in-env").encode("utf-8")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

DEV_TOKEN_ENABLED = os.getenv("DEV_TOKEN_ENABLED", "false").lower() == "true"
DEV_TOKEN_KEY = os.getenv("DEV_TOKEN_KEY", "")
DEV_FORCE_ACTIVE = os.getenv("DEV_FORCE_ACTIVE", "false").lower() == "true"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def make_token(email: str, ttl_seconds: int = 24 * 3600) -> str:
    """
    Signed token: base64url(payload).base64url(sig)
    payload = {"e": email, "exp": epoch, "n": nonce}
    """
    exp = int(time.time()) + int(ttl_seconds)
    payload = {"e": email.strip().lower(), "exp": exp, "n": secrets.token_hex(8)}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(TOKEN_SECRET, raw, hashlib.sha256).digest()
    return f"{_b64url(raw)}.{_b64url(sig)}"

def verify_token(token: str) -> Dict[str, Any]:
    try:
        a, b = token.split(".", 1)
        raw = _b64url_decode(a)
        sig = _b64url_decode(b)
        exp_sig = hmac.new(TOKEN_SECRET, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, exp_sig):
            raise ValueError("bad signature")
        payload = json.loads(raw.decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired")
        email = str(payload.get("e", "")).strip().lower()
        if not email or "@" not in email:
            raise ValueError("bad email")
        return payload
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid or expired link.")

def token_email_or_403(token: str) -> str:
    payload = verify_token(token)
    return str(payload["e"]).strip().lower()

def absolute(url_path: str) -> str:
    # For emails later; for now good for debugging
    if BASE_URL:
        return f"{BASE_URL}{url_path}"
    return url_path

def init_tables() -> None:
    conn = db()
    cur = conn.cursor()

    # Subscriber access grants (from Stripe webhook OR dev force)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS access_grants (
            email TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
    """)

    # Public lead form submissions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            interest TEXT,
            phone TEXT,
            company TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Partner / sponsor submissions
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

    # Subscriber intake (token-protected)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriber_intakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auth_email TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            service_requested TEXT NOT NULL,
            notes TEXT,
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

init_tables()


def is_active_subscriber(email: str) -> bool:
    email = email.strip().lower()
    if DEV_FORCE_ACTIVE:
        return True
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM access_grants WHERE email = ?", (email,))
    ok = cur.fetchone() is not None
    conn.close()
    return ok


# ------------------------------------------------------------
# Scoring + Rails
# ------------------------------------------------------------

def score_contributor(track: str,
                      comp_plan: Optional[str],
                      assets: Optional[str],
                      website: Optional[str],
                      company: Optional[str],
                      fit_fields: List[Optional[str]],
                      fit_authority: Optional[str]) -> int:
    score = 0
    t = (track or "").strip().lower()

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
    score += track_weights.get(t, 10)

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

    auth = (fit_authority or "").strip().lower()
    if auth == "owner_exec":
        score += 10
    elif auth == "manager_influence":
        score += 6
    elif auth == "partial":
        score += 3

    return int(score)

def assign_rail(track: str,
                score: int,
                position_interest: Optional[str],
                fit_lane: Optional[str]) -> str:
    t = (track or "").strip().lower()
    pos = (position_interest or "").strip().lower()
    lane = (fit_lane or "").strip().lower()

    if score >= 70:
        if t == "sales_growth" or lane == "sales" or "sales" in pos or "closer" in pos:
            return "sales_priority"
        if t == "ecosystem_staff" or "intake" in pos or "ops" in pos or "client_success" in pos:
            return "staff_priority"
        if t == "hardware_supply" or lane == "hardware":
            return "hardware_supply"
        if t == "capital_sponsor" or lane in ("finance", "capital"):
            return "capital"
        return "priority"

    if score >= 45:
        if t == "sales_growth":
            return "sales_pool"
        if t == "ecosystem_staff":
            return "staff_pool"
        if t in ("partner_vendor", "hardware_supply"):
            return "bd_followup"
        return "review"

    return "triage"


# ------------------------------------------------------------
# Core Pages
# ------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "year": datetime.now().year})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request, "year": datetime.now().year})

@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request, "year": datetime.now().year})

@app.post("/lead")
async def lead_submit(
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
        INSERT INTO leads (name, email, interest, phone, company, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, email, interest, phone, company, message, now_iso()))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/lead?ok=1", status_code=303)

@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request, "year": datetime.now().year})

@app.post("/partner")
async def partner_submit(
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
    return RedirectResponse(url="/partner?ok=1", status_code=303)


# ------------------------------------------------------------
# Stripe Checkout + Success/Cancel
# ------------------------------------------------------------

def stripe_ready() -> bool:
    return bool(stripe and STRIPE_SECRET_KEY and STRIPE_PRICE_ID)

@app.get("/checkout")
def checkout():
    if not stripe_ready():
        return RedirectResponse(url="/services?stripe=not_configured", status_code=303)

    stripe.api_key = STRIPE_SECRET_KEY

    success_url = absolute("/success?session_id={CHECKOUT_SESSION_ID}")
    cancel_url = absolute("/cancel")

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
    )
    return RedirectResponse(url=session.url, status_code=303)

@app.get("/success", response_class=HTMLResponse)
def success(request: Request, session_id: Optional[str] = None):
    """
    If Stripe is configured and session_id is present, we fetch email and generate a token link.
    If Stripe isn't configured, we just render the template without token.
    """
    email = None
    dashboard_link = None
    token = None

    if stripe_ready() and session_id:
        stripe.api_key = STRIPE_SECRET_KEY
        try:
            sess = stripe.checkout.Session.retrieve(session_id)
            # best effort email extraction
            email = (sess.get("customer_details", {}) or {}).get("email") or sess.get("customer_email")
            if email:
                email = str(email).strip().lower()

                # Create access grant immediately (even before webhook)
                conn = db()
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO access_grants (email, created_at) VALUES (?, ?)", (email, now_iso()))
                conn.commit()
                conn.close()

                token = make_token(email)
                dashboard_link = f"/dashboard?token={token}"
        except Exception:
            pass

    return templates.TemplateResponse(
        "success.html",
        {
            "request": request,
            "year": datetime.now().year,
            "email": email,
            "dashboard_link": dashboard_link,
            "token": token,  # template should NOT display raw token; only use it inside links
        },
    )

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request, "year": datetime.now().year})


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe webhook to grant access when payment completes.
    """
    if not stripe or not STRIPE_WEBHOOK_SECRET or not STRIPE_SECRET_KEY:
        return PlainTextResponse("Stripe not configured", status_code=400)

    stripe.api_key = STRIPE_SECRET_KEY
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("type", "")
    obj = (event.get("data", {}) or {}).get("object", {}) or {}

    # Most important for access:
    if event_type in ("checkout.session.completed", "invoice.paid"):
        email = None

        if event_type == "checkout.session.completed":
            email = (obj.get("customer_details", {}) or {}).get("email") or obj.get("customer_email")
        elif event_type == "invoice.paid":
            # invoice has customer_email sometimes; otherwise you'd fetch customer
            email = obj.get("customer_email")

        if email:
            email = str(email).strip().lower()
            conn = db()
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO access_grants (email, created_at) VALUES (?, ?)", (email, now_iso()))
            conn.commit()
            conn.close()

    return JSONResponse({"ok": True})


# ------------------------------------------------------------
# Token-Protected Subscriber Area
# ------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str):
    auth_email = token_email_or_403(token)
    if not is_active_subscriber(auth_email):
        raise HTTPException(status_code=403, detail="Invalid or expired link.")
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "year": datetime.now().year, "email": auth_email, "token": token},
    )

@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str):
    auth_email = token_email_or_403(token)
    if not is_active_subscriber(auth_email):
        raise HTTPException(status_code=403, detail="Invalid or expired link.")
    return templates.TemplateResponse(
        "intake_form.html",
        {"request": request, "year": datetime.now().year, "email": auth_email, "token": token},
    )

@app.post("/intake")
async def submit_intake(
    token: str,
    name: str = Form(...),
    email: str = Form(...),
    service_requested: str = Form(...),
    notes: str = Form(""),
):
    auth_email = token_email_or_403(token)
    if not is_active_subscriber(auth_email):
        raise HTTPException(status_code=403, detail="Invalid or expired link.")

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO subscriber_intakes (auth_email, name, email, service_requested, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (auth_email, name, email, service_requested, notes, now_iso()))
    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/dashboard?token={token}&intake=ok", status_code=303)


# ------------------------------------------------------------
# Admin Intake JSON (simple)
# ------------------------------------------------------------

@app.get("/admin/intake")
def admin_intake_json(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, auth_email, name, email, service_requested, notes, created_at
        FROM subscriber_intakes
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse({"count": len(rows), "items": rows})


# ------------------------------------------------------------
# Contributor Intake + Save
# ------------------------------------------------------------

@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request, "year": datetime.now().year})

@app.post("/contributor")
async def submit_contributor(
    # Core
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    company: str = Form(""),
    website: str = Form(""),

    # Role + Track
    primary_role: str = Form(...),
    contribution_track: str = Form(...),
    position_interest: str = Form(""),
    comp_plan: str = Form(""),
    director_owner: str = Form("Duece"),  # ✅ corrected spelling

    # Capacity
    assets: str = Form(""),
    regions: str = Form(""),
    capacity: str = Form(""),
    alignment: str = Form(""),
    message: str = Form(""),

    # Fit Extract (optional)
    fit_access: str = Form(""),
    fit_build_goal: str = Form(""),
    fit_opportunity: str = Form(""),
    fit_authority: str = Form(""),
    fit_lane: str = Form(""),
    fit_no_conditions: str = Form(""),
    fit_visibility: str = Form(""),
    fit_why_you: str = Form(""),
):
    fit_fields = [
        fit_access, fit_build_goal, fit_opportunity, fit_authority,
        fit_lane, fit_no_conditions, fit_visibility, fit_why_you
    ]

    score = score_contributor(
        track=contribution_track,
        comp_plan=comp_plan,
        assets=assets,
        website=website,
        company=company,
        fit_fields=fit_fields,
        fit_authority=fit_authority,
    )
    rail = assign_rail(
        track=contribution_track,
        score=score,
        position_interest=position_interest,
        fit_lane=fit_lane,
    )

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
        name, email.strip().lower(), phone, company, website,
        primary_role,
        contribution_track, position_interest, comp_plan, director_owner,
        assets, regions, capacity, alignment, message,
        fit_access, fit_build_goal, fit_opportunity, fit_authority,
        fit_lane, fit_no_conditions, fit_visibility, fit_why_you,
        score, rail, "new", now_iso()
    ))
    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/contributor?ok=1&rail={rail}&score={score}", status_code=303)


# ------------------------------------------------------------
# Contributor Admin Dashboard + Status Update
# ------------------------------------------------------------

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
    params: List[Any] = []

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
        {
            "request": request,
            "contributors": rows,
            "rail": rail,
            "min_score": min_score,
            "track": track,
            "year": datetime.now().year,
        },
    )

@app.post("/admin/contributor-status")
async def update_contributor_status(
    id: int = Form(...),
    status: str = Form(...),
):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE contributors SET status = ? WHERE id = ?", (status, int(id)))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin/contributors-dashboard", status_code=303)


# ------------------------------------------------------------
# Dev Token Generator (locked)
# ------------------------------------------------------------

@app.get("/dev/generate-token")
def dev_generate_token(email: str, key: str):
    """
    Usage:
      /dev/generate-token?email=youremail@example.com&key=DEV_TOKEN_KEY
    Returns JSON with token + dashboard link.
    """
    if not DEV_TOKEN_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    if not DEV_TOKEN_KEY or key != DEV_TOKEN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    e = email.strip().lower()
    if not e or "@" not in e:
        raise HTTPException(status_code=400, detail="Bad email")

    # Optional: force access grant so link always works (helps demos)
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO access_grants (email, created_at) VALUES (?, ?)", (e, now_iso()))
    conn.commit()
    conn.close()

    token = make_token(e)
    return JSONResponse({
        "email": e,
        "token": token,
        "dashboard": absolute(f"/dashboard?token={token}"),
        "intake": absolute(f"/intake-form?token={token}"),
    })
