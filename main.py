import os
import logging
from pathlib import Path
from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND

# ----------------------------
# Setup
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nautical-compass")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Nautical Compass Intake", version="0.1.0")

# Mount static if folder exists (prevents crashes if missing)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info("Static mounted: %s", STATIC_DIR)
else:
    logger.warning("Static folder not found at %s (site will still run, but no assets).", STATIC_DIR)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ----------------------------
# Global safety net (prevents 500 loops)
# ----------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "server_error", "path": request.url.path},
    )

# ----------------------------
# Health check (use this in DO health checks)
# ----------------------------
@app.get("/health")
def health():
    return {"ok": True}

# ----------------------------
# Core pages
# ----------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # Make sure templates/index.html exists
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return templates.TemplateResponse("services.html", {"request": request})

@app.get("/hall", response_class=HTMLResponse)
def hall(request: Request):
    # Make sure templates/hall.html exists
    return templates.TemplateResponse("hall.html", {"request": request})

# ----------------------------
# Lead intake (simple)
# ----------------------------
@app.get("/lead", response_class=HTMLResponse)
def lead_page(request: Request):
    return templates.TemplateResponse("lead_intake.html", {"request": request})

@app.post("/lead")
def lead_submit(
    name: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    message: str = Form(None),
):
    # Keep simple: log + return ok (don’t break prod)
    logger.info("Lead: name=%s email=%s phone=%s", name, email, phone)
    return RedirectResponse(url="/lead/thanks", status_code=HTTP_302_FOUND)

@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return templates.TemplateResponse("lead_thanks.html", {"request": request})

# ----------------------------
# Partner intake
# ----------------------------
@app.get("/partner", response_class=HTMLResponse)
def partner_page(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request})

@app.post("/partner")
def partner_submit(
    company: str = Form(None),
    contact: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    message: str = Form(None),
):
    logger.info("Partner: company=%s contact=%s email=%s", company, contact, email)
    return RedirectResponse(url="/partner/thanks", status_code=HTTP_302_FOUND)

@app.get("/partner/thanks", response_class=HTMLResponse)
def partner_thanks(request: Request):
    return templates.TemplateResponse("partner_thanks.html", {"request": request})

# ----------------------------
# Sponsor page (checkout handled elsewhere if needed)
# ----------------------------
@app.get("/sponsor", response_class=HTMLResponse)
def sponsor_page(request: Request):
    return templates.TemplateResponse("sponsor.html", {"request": request})

# ----------------------------
# AVPT + LMT intakes (HTML forms)
# ----------------------------
@app.get("/intake/production", response_class=HTMLResponse)
def intake_production(request: Request):
    return templates.TemplateResponse("intake_production.html", {"request": request})

@app.post("/intake/production")
def submit_production(request: Request):
    # Don’t blow up if form changes — accept and route
    return RedirectResponse(url="/dash/production", status_code=HTTP_302_FOUND)

@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor(request: Request):
    return templates.TemplateResponse("intake_labor.html", {"request": request})

@app.post("/intake/labor")
def submit_labor(request: Request):
    return RedirectResponse(url="/dash/labor", status_code=HTTP_302_FOUND)

# ----------------------------
# Dashboards
# ----------------------------
@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    return templates.TemplateResponse("dashboards.html", {"request": request})

@app.get("/dash/production", response_class=HTMLResponse)
def dash_production(request: Request):
    return templates.TemplateResponse("dash_production.html", {"request": request})

@app.get("/dash/labor", response_class=HTMLResponse)
def dash_labor(request: Request):
    return templates.TemplateResponse("dash_labor.html", {"request": request})

# ----------------------------
# Run locally (DO uses its own start command)
# ----------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
