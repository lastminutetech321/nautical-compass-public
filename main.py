from pathlib import Path
import time

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Nautical Compass")

UPLOAD_ROOT = Path("uploads")
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="uploads")

templates = Jinja2Templates(directory="templates")

PRODUCTION_SUBMISSIONS = []
LABOR_SUBMISSIONS = []
PARTNER_SUBMISSIONS = []


def render(request: Request, template: str, data=None):
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return templates.TemplateResponse(template, ctx)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "index.html")


@app.get("/hall", response_class=HTMLResponse)
def hall(request: Request):
    return render(request, "hall.html")


@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return render(request, "services.html")


@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    return render(request, "dashboards_hub.html")


@app.get("/lead", response_class=HTMLResponse)
def lead(request: Request):
    return render(request, "lead_intake.html")


@app.post("/lead")
def lead_submit(
    name: str = Form(""),
    email: str = Form(""),
    message: str = Form("")
):
    return RedirectResponse("/lead/thanks", status_code=303)


@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return render(request, "lead_thanks.html")


@app.get("/sponsor", response_class=HTMLResponse)
def sponsor(request: Request):
    return render(request, "sponsor.html")


@app.get("/checkout")
def checkout():
    return JSONResponse({"ok": True, "message": "Checkout placeholder active."})


@app.get("/partner", response_class=HTMLResponse)
def partner(request: Request):
    return render(request, "partner_intake.html")


@app.post("/partner")
async def partner_submit(
    request: Request,
    company_name: str = Form(""),
    contact_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    category: str = Form(""),
    territory: str = Form(""),
    capabilities: str = Form(""),
    notes: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    submission_id = len(PARTNER_SUBMISSIONS) + 1

    PARTNER_SUBMISSIONS.append(
        {
            "id": submission_id,
            "company_name": company_name,
            "contact_name": contact_name,
            "email": email,
            "phone": phone,
            "category": category,
            "territory": territory,
            "capabilities": capabilities,
            "notes": notes,
            "file_count": len(files),
            "created_at": int(time.time()),
        }
    )

    return render(
        request,
        "submission_success.html",
        {
            "title": "Partner Port Submission Received",
            "summary": "Your partner or manufacturer intake has been captured and routed into the system.",
            "return_href": "/services",
            "return_label": "Back to Service Ports",
            "next_href": "/dashboards",
            "next_label": "Open Operations Deck",
            "record_id": submission_id,
            "file_count": len(files),
            "step_number": 1,
            "step_total": 1,
            "step_name": "Partner Port",
            "why_next": "Your partner record is captured. The next useful place is the Operations Deck so you can review where this lane sits in the wider system.",
        },
    )


@app.get("/intake/production", response_class=HTMLResponse)
def intake_production(request: Request):
    return render(request, "intake_production.html")


@app.post("/intake/production")
async def intake_production_submit(
    request: Request,
    company_name: str = Form(""),
    contact_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    event_name: str = Form(""),
    event_type: str = Form(""),
    event_location: str = Form(""),
    event_dates: str = Form(""),
    crew_needed: str = Form(""),
    logistics_notes: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    submission_id = len(PRODUCTION_SUBMISSIONS) + 1

    PRODUCTION_SUBMISSIONS.append(
        {
            "id": submission_id,
            "company_name": company_name,
            "contact_name": contact_name,
            "email": email,
            "phone": phone,
            "event_name": event_name,
            "event_type": event_type,
            "event_location": event_location,
            "event_dates": event_dates,
            "crew_needed": crew_needed,
            "logistics_notes": logistics_notes,
            "file_count": len(files),
            "created_at": int(time.time()),
        }
    )

    return render(
        request,
        "submission_success.html",
        {
            "title": "Production Request Received",
            "summary": "The production command intake has been captured for crew and logistics routing.",
            "return_href": "/services",
            "return_label": "Back to Service Ports",
            "next_href": "/intake/labor",
            "next_label": "Continue to Labor Dispatch",
            "record_id": submission_id,
            "file_count": len(files),
            "step_number": 1,
            "step_total": 3,
            "step_name": "Production Command",
            "why_next": "Production needs to connect to workforce supply. Labor Dispatch is the next lane where worker-side readiness and role coverage can be aligned.",
        },
    )


@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor(request: Request):
    return render(request, "intake_labor.html")


@app.post("/intake/labor")
async def intake_labor_submit(
    request: Request,
    full_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    primary_role: str = Form(""),
    certifications: str = Form(""),
    market_area: str = Form(""),
    availability: str = Form(""),
    transport: str = Form(""),
    notes: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    submission_id = len(LABOR_SUBMISSIONS) + 1

    LABOR_SUBMISSIONS.append(
        {
            "id": submission_id,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "primary_role": primary_role,
            "certifications": certifications,
            "market_area": market_area,
            "availability": availability,
            "transport": transport,
            "notes": notes,
            "file_count": len(files),
            "created_at": int(time.time()),
        }
    )

    return render(
        request,
        "submission_success.html",
        {
            "title": "Labor Dispatch Intake Received",
            "summary": "Your workforce profile has been captured for dispatch readiness and route matching.",
            "return_href": "/services",
            "return_label": "Back to Service Ports",
            "next_href": "/dashboards",
            "next_label": "Open Operations Deck",
            "record_id": submission_id,
            "file_count": len(files),
            "step_number": 2,
            "step_total": 3,
            "step_name": "Labor Dispatch",
            "why_next": "The worker profile is now staged. The deck is the best place to monitor how operator and client lanes will connect as the system deepens.",
        },
    )


@app.get("/modules/case-dock", response_class=HTMLResponse)
def case_dock(request: Request):
    return render(request, "case_dock.html")


@app.post("/modules/case-dock")
async def case_dock_submit(
    request: Request,
    matter_title: str = Form(""),
    jurisdiction: str = Form(""),
    issue_type: str = Form(""),
    parties: str = Form(""),
    timeline: str = Form(""),
    summary: str = Form(""),
    requested_outcome: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    return render(
        request,
        "submission_success.html",
        {
            "title": "Case Dock Intake Received",
            "summary": "Your case was received and staged for the next legal step.",
            "return_href": "/services",
            "return_label": "Back to Service Ports",
            "next_href": "/modules/signal-dock",
            "next_label": "Continue to Signal Dock",
            "record_id": 1,
            "file_count": len(files),
            "step_number": 1,
            "step_total": 4,
            "step_name": "Case Dock",
            "why_next": "Signal Dock is next because it reviews deadlines, notices, triggers, and risk signals before remedy analysis.",
        },
    )


@app.get("/modules/signal-dock", response_class=HTMLResponse)
def signal_dock(request: Request):
    return render(request, "signal_dock.html")


@app.get("/modules/equity-engine", response_class=HTMLResponse)
def equity_engine(request: Request):
    return render(request, "equity_engine.html")


@app.get("/modules/navigator-ai", response_class=HTMLResponse)
def navigator_ai(request: Request):
    return render(request, "navigator_ai.html", {"case_context": None})
