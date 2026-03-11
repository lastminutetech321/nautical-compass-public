import os
import hmac
import time
import json
import base64
import hashlib
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


APP_NAME = "Nautical Compass Intake"
APP_VERSION = "0.1.0"

ADMIN_KEY = os.getenv("ADMIN_KEY", "")  # set in DigitalOcean env vars
TOKEN_SECRET = os.getenv("TOKEN_SECRET", ADMIN_KEY or "dev-secret")  # fallback, but set it for real

# In-memory stores (good for MVP; later move to DB)
LEADS = []
PARTNERS = []
PRODUCTION_REQUESTS = []
LABOR_PROFILES = []
GENERIC_INTAKES = []


app = FastAPI(title=APP_NAME, version=APP_VERSION)

# ✅ Critical: mount /static so images/css/js work
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


# ------------------------
# Helpers
# ------------------------
def _template_exists(name: str) -> bool:
    try:
        templates.get_template(name)
        return True
    except Exception:
        return False


def render(request: Request, preferred: str, fallback: str = "index.html", **ctx):
    name = preferred if _template_exists(preferred) else fallback
    return templates.TemplateResponse(name, {"request": request, **ctx})


def ok_json(data: Dict[str, Any]):
    return JSONResponse(content=data)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _sign(payload: Dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(TOKEN_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    return _b64url(body) + "." + _b64url(sig)


def _verify(token: str) -> Optional[Dict[str, Any]]:
    try:
        body_b64, sig_b64 = token.split(".", 1)
        pad1 = "=" * (-len(body_b64) % 4)
        pad2 = "=" * (-len(sig_b64) % 4)
        body = base64.urlsafe_b64decode((body_b64 + pad1).encode("utf-8"))
        sig = base64.urlsafe_b64decode((sig_b64 + pad2).encode("utf-8"))

        expected = hmac.new(TOKEN_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None

        payload = json.loads(body.decode("utf-8"))
        # optional expiry handling
        exp = payload.get("exp")
        if exp and time.time() > float(exp):
            return None
        return payload
    except Exception:
        return None


def _admin_ok(k: Optional[str], key: Optional[str]) -> bool:
    candidate = (k or key or "").strip()
    return bool(ADMIN_KEY) and candidate == ADMIN_KEY


# ------------------------
# Public pages
# ------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # You want captain view on the intro page -> use index.html (your repo has it)
    return render(request, "index.html", "index.html")


@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return render(request, "services.html", "index.html")


@app.get("/hall", response_class=HTMLResponse)
def hall(request: Request):
    # You already built hall.html; keep it the hall page.
    return render(request, "hall.html", "index.html")


@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    # Your repo shows dashboards_hub.html + dashboards.html exists sometimes.
    if _template_exists("dashboards.html"):
        return render(request, "dashboards.html", "index.html")
    return render(request, "dashboards_hub.html", "index.html")


@app.get("/dash/production", response_class=HTMLResponse)
def dash_production(request: Request):
    return render(request, "dash_production.html", "dashboards_hub.html")


@app.get("/dash/labor", response_class=HTMLResponse)
def dash_labor(request: Request):
    return render(request, "dash_labor.html", "dashboards_hub.html")


# ------------------------
# Lead intake (simple)
# ------------------------
@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return render(request, "lead_intake.html", "lead_intake.html" if _template_exists("lead_intake.html") else "index.html")


@app.post("/lead")
def lead_submit(
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    message: str = Form(""),
):
    LEADS.append({"ts": time.time(), "name": name, "email": email, "phone": phone, "message": message})
    return RedirectResponse(url="/lead/thanks", status_code=303)


@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return render(request, "lead_thanks.html", "index.html")


# ------------------------
# Partner intake
# ------------------------
@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return render(request, "partner_intake.html", "partner_intake.html" if _template_exists("partner_intake.html") else "index.html")


@app.post("/partner")
def partner_submit(
    company: str = Form(""),
    contact: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    product: str = Form(""),
    region: str = Form(""),
    notes: str = Form(""),
):
    PARTNERS.append(
        {"ts": time.time(), "company": company, "contact": contact, "email": email, "phone": phone, "product": product, "region": region, "notes": notes}
    )
    return RedirectResponse(url="/partner/thanks", status_code=303)


@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return render(request, "partner_thanks.html", "index.html")


# ------------------------
# Sponsor page + checkout (safe stub)
# ------------------------
@app.get("/sponsor", response_class=HTMLResponse)
def sponsor_page(request: Request):
    return render(request, "sponsor.html", "index.html")


@app.get("/sponsor/checkout")
def sponsor_checkout(ref: Optional[str] = Query(default=None)):
    # Keep as stub unless you wire Stripe
    return ok_json({"ok": True, "mode": "sponsor_checkout_stub", "ref": ref})


# ------------------------
# Generic tokenized intake flow (kept to match your OpenAPI)
# ------------------------
@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request, token: str = Query(...)):
    payload = _verify(token)
    if not payload:
        return HTMLResponse("Invalid or expired token.", status_code=401)
    return render(request, "intake_form.html", "index.html", token=token, payload=payload)


@app.post("/intake")
def submit_intake(token: str = Query(...), payload_json: str = Form("{}")):
    payload = _verify(token)
    if not payload:
        return JSONResponse({"ok": False, "error": "invalid_token"}, status_code=401)

    try:
        data = json.loads(payload_json) if payload_json else {}
    except Exception:
        data = {"raw": payload_json}

    rec_id = len(GENERIC_INTAKES) + 1
    GENERIC_INTAKES.append({"id": rec_id, "ts": time.time(), "token_payload": payload, "data": data})
    return ok_json({"ok": True, "id": rec_id})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: str = Query(...)):
    payload = _verify(token)
    if not payload:
        return HTMLResponse("Invalid or expired token.", status_code=401)
    return render(request, "dashboard.html", "dashboards_hub.html", token=token, payload=payload)


# ------------------------
# AVPT production intake
# ------------------------
@app.get("/intake/production", response_class=HTMLResponse)
def intake_production(request: Request):
    return render(request, "intake_production.html", "index.html")


@app.post("/intake/production")
def submit_production(
    company: str = Form(""),
    contact: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    venue: str = Form(""),
    city: str = Form(""),
    date: str = Form(""),
    call_time: str = Form(""),
    roles_needed: str = Form(""),
    notes: str = Form(""),
):
    rec_id = len(PRODUCTION_REQUESTS) + 1
    PRODUCTION_REQUESTS.append(
        {
            "id": rec_id,
            "ts": time.time(),
            "company": company,
            "contact": contact,
            "email": email,
            "phone": phone,
            "venue": venue,
            "city": city,
            "date": date,
            "call_time": call_time,
            "roles_needed": roles_needed,
            "notes": notes,
        }
    )
    return RedirectResponse(url=f"/results?lane=avpt&id={rec_id}", status_code=303)


# ------------------------
# LMT labor intake
# ------------------------
@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor(request: Request):
    return render(request, "intake_labor.html", "index.html")


@app.post("/intake/labor")
def submit_labor(
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    city: str = Form(""),
    roles: str = Form(""),
    certs: str = Form(""),
    transportation: str = Form(""),
    availability: str = Form(""),
    notes: str = Form(""),
):
    rec_id = len(LABOR_PROFILES) + 1
    LABOR_PROFILES.append(
        {
            "id": rec_id,
            "ts": time.time(),
            "name": name,
            "email": email,
            "phone": phone,
            "city": city,
            "roles": roles,
            "certs": certs,
            "transportation": transportation,
            "availability": availability,
            "notes": notes,
        }
    )
    return RedirectResponse(url=f"/results?lane=lmt&id={rec_id}", status_code=303)


# ------------------------
# Results (lane-specific template if available)
# ------------------------
@app.get("/results", response_class=HTMLResponse)
def results(request: Request, lane: str = Query(...), id: int = Query(...)):
    lane_key = (lane or "").lower()

    ctx = {"lane": lane_key, "id": id}

    if lane_key in ("avpt", "production"):
        item = next((x for x in PRODUCTION_REQUESTS if x["id"] == id), None)
        ctx["item"] = item
        if _template_exists("results_avpt.html"):
            return render(request, "results_avpt.html", "results.html", **ctx)
        return render(request, "results.html", "index.html", **ctx)

    if lane_key in ("lmt", "labor", "tech"):
        item = next((x for x in LABOR_PROFILES if x["id"] == id), None)
        ctx["item"] = item
        if _template_exists("results_lmt.html"):
            return render(request, "results_lmt.html", "results.html", **ctx)
        return render(request, "results.html", "index.html", **ctx)

    # default
    item = next((x for x in GENERIC_INTAKES if x["id"] == id), None)
    ctx["item"] = item
    return render(request, "results.html", "index.html", **ctx)


# ------------------------
# Checkout/success/cancel (safe stubs)
# ------------------------
@app.get("/checkout")
def checkout(ref: Optional[str] = Query(default=None)):
    return ok_json({"ok": True, "mode": "checkout_stub", "ref": ref})


@app.get("/success", response_class=HTMLResponse)
def success(request: Request, session_id: Optional[str] = Query(default=None)):
    return render(request, "success.html", "index.html", session_id=session_id)


@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return render(request, "cancel.html", "index.html")


@app.post("/stripe/webhook")
def stripe_webhook():
    return ok_json({"ok": True})


@app.post("/webhook/stripe")
def stripe_webhook_alias():
    return ok_json({"ok": True})


# ------------------------
# Admin dashboards (key required)
# ------------------------
@app.get("/admin/leads-dashboard", response_class=HTMLResponse)
def leads_dashboard(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    if not _admin_ok(k, key):
        return HTMLResponse("Unauthorized", status_code=401)
    return render(request, "admin_leads.html", "admin_leads.html" if _template_exists("admin_leads.html") else "index.html", rows=LEADS)


@app.get("/admin/partners-dashboard", response_class=HTMLResponse)
def partners_dashboard(
    request: Request,
    k: Optional[str] = None,
    key: Optional[str] = None,
    q: str = "",
    product: str = "",
    region: str = "",
):
    if not _admin_ok(k, key):
        return HTMLResponse("Unauthorized", status_code=401)

    rows = PARTNERS[:]
    if q:
        qq = q.lower()
        rows = [r for r in rows if qq in (r.get("company", "").lower() + " " + r.get("contact", "").lower() + " " + r.get("notes", "").lower())]
    if product:
        pp = product.lower()
        rows = [r for r in rows if pp in r.get("product", "").lower()]
    if region:
        rr = region.lower()
        rows = [r for r in rows if rr in r.get("region", "").lower()]

    return render(
        request,
        "partners_dashboard.html",
        "partners_dashboard.html" if _template_exists("partners_dashboard.html") else "index.html",
        rows=rows,
        q=q,
        product=product,
        region=region,
    )


@app.get("/admin/contributors-dashboard", response_class=HTMLResponse)
def contributors_dashboard(
    request: Request,
    k: Optional[str] = None,
    key: Optional[str] = None,
    rail: Optional[str] = None,
    min_score: Optional[int] = None,
    track: Optional[str] = None,
):
    if not _admin_ok(k, key):
        return HTMLResponse("Unauthorized", status_code=401)
    # placeholder view if you have it
    return render(
        request,
        "admin_contributors.html",
        "admin_contributors.html" if _template_exists("admin_contributors.html") else "index.html",
        rows=[],
        rail=rail,
        min_score=min_score,
        track=track,
    )


@app.post("/admin/contributor-status")
def update_contributor_status():
    return ok_json({"ok": True})


@app.get("/admin/people-dashboard", response_class=HTMLResponse)
def people_dashboard(request: Request, k: Optional[str] = None, key: Optional[str] = None):
    if not _admin_ok(k, key):
        return HTMLResponse("Unauthorized", status_code=401)
    return render(
        request,
        "admin_people.html",
        "admin_people.html" if _template_exists("admin_people.html") else "index.html",
        production=PRODUCTION_REQUESTS,
        labor=LABOR_PROFILES,
        leads=LEADS,
        partners=PARTNERS,
    )


@app.post("/admin/create-operator")
def create_operator():
    return ok_json({"ok": True})


# ------------------------
# Contributor (stub)
# ------------------------
@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return render(request, "contributor_portal.html", "index.html")


@app.post("/contributor")
def submit_contributor():
    return ok_json({"ok": True})


# ------------------------
# Dev: generate token (admin key required)
# ------------------------
@app.get("/dev/generate-token")
def dev_generate_token(email: str = Query(...), key: str = Query(...)):
    # Only allow if provided key matches ADMIN_KEY (or TOKEN_SECRET if you prefer)
    if not ADMIN_KEY or key.strip() != ADMIN_KEY:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    payload = {
        "email": email,
        "iat": time.time(),
        "exp": time.time() + (60 * 60 * 24),  # 24 hours
    }
    token = _sign(payload)
    return ok_json({"ok": True, "token": token, "payload": payload})
