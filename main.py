import os
import time
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

# --- Static + Templates (CRITICAL) ---
# Must exist as folders in repo:
#   /static
#   /templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Helpers ---
def nocache_template(request: Request, template_name: str, context: dict):
    # Cache-buster token so your iPad doesn't show old CSS/JS
    ctx = dict(context)
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return templates.TemplateResponse(template_name, ctx)

# --- Pages ---
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return nocache_template(request, "index.html", {})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    # If you already have templates/services.html, it will render.
    # If not, create it later.
    return nocache_template(request, "services.html", {})

@app.get("/hall", response_class=HTMLResponse)
def hall(request: Request):
    return nocache_template(request, "hall.html", {})

@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return nocache_template(request, "lead_intake.html", {})

@app.post("/lead")
def lead_submit(
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    message: str = Form(""),
):
    # Keep simple for now (no DB). You can wire storage later.
    return RedirectResponse(url="/lead/thanks", status_code=303)

@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return nocache_template(request, "lead_thanks.html", {})

@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return nocache_template(request, "partner_intake.html", {})

@app.post("/partner")
def partner_submit(
    company: str = Form(""),
    contact: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    notes: str = Form(""),
):
    return RedirectResponse(url="/partner/thanks", status_code=303)

@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return nocache_template(request, "partner_thanks.html", {})

@app.get("/sponsor", response_class=HTMLResponse)
def sponsor_page(request: Request):
    return nocache_template(request, "sponsor.html", {})

# --- Intake pages (AVPT/LMT) ---
@app.get("/intake/production", response_class=HTMLResponse)
def intake_production(request: Request):
    return nocache_template(request, "intake_production.html", {})

@app.post("/intake/production")
def submit_production():
    return JSONResponse({"ok": True})

@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor(request: Request):
    return nocache_template(request, "intake_labor.html", {})

@app.post("/intake/labor")
def submit_labor():
    return JSONResponse({"ok": True})

# --- Dashboards (FIXES "detail not found") ---
@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    # This file exists in your repo screenshots: templates/dashboards_hub.html
    return nocache_template(request, "dashboards_hub.html", {})

@app.get("/dash/production", response_class=HTMLResponse)
def dash_production(request: Request):
    return nocache_template(request, "dash_production.html", {})

@app.get("/dash/labor", response_class=HTMLResponse)
def dash_labor(request: Request):
    return nocache_template(request, "dash_labor.html", {})

# --- Simple results route used by your OpenAPI ---
@app.get("/results", response_class=HTMLResponse)
def results(request: Request, lane: str, id: int):
    return nocache_template(request, "results.html", {"lane": lane, "id": id})

# --- Payments placeholders (safe stubs) ---
@app.get("/checkout")
def checkout(ref: Optional[str] = None):
    # Wire Stripe later. Keep endpoint alive.
    return JSONResponse({"ok": True, "ref": ref})

@app.get("/success", response_class=HTMLResponse)
def success(request: Request, session_id: Optional[str] = None):
    return nocache_template(request, "success.html", {"session_id": session_id})

@app.get("/cancel", response_class=HTMLResponse)
def cancel(request: Request):
    return nocache_template(request, "cancel.html", {})

@app.post("/stripe/webhook")
def stripe_webhook():
    return JSONResponse({"ok": True})

@app.post("/webhook/stripe")
def stripe_webhook_alias():
    return JSONResponse({"ok": True})
