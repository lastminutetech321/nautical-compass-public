"""
Legal Services UI Routes — informational pages + live analysis pages.

Analysis pages (standing, capacity) accept optional POST and display
structured results from the analysis services.
"""
import time
import logging

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")
legal_router = APIRouter()


def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return ctx


def _run_standing(intake_state: dict, complaint_id: str | None) -> dict:
    try:
        from services.standing_analysis_service import analyze_standing
        return analyze_standing(intake_state, complaint_id)
    except Exception as exc:
        logger.warning("standing analysis failed: %s", exc)
        return {"error": str(exc)}


def _run_capacity(intake_state: dict, complaint_id: str | None) -> dict:
    try:
        from services.capacity_analysis_service import analyze_capacity
        return analyze_capacity(intake_state, complaint_id)
    except Exception as exc:
        logger.warning("capacity analysis failed: %s", exc)
        return {"error": str(exc)}


# ── informational pages ──────────────────────────────────────────────────────

@legal_router.get("/legal-services", response_class=HTMLResponse)
def legal_services_hub(request: Request):
    return templates.TemplateResponse(request, "legal_services.html", context=_ctx(request))


@legal_router.get("/section-1983", response_class=HTMLResponse)
def section_1983_page(request: Request):
    return templates.TemplateResponse(request, "section_1983.html", context=_ctx(request))


@legal_router.get("/consumer-rights", response_class=HTMLResponse)
def consumer_rights_page(request: Request):
    return templates.TemplateResponse(request, "consumer_rights.html", context=_ctx(request))


@legal_router.get("/status-correction", response_class=HTMLResponse)
def status_correction_page(request: Request):
    return templates.TemplateResponse(request, "status_correction.html", context=_ctx(request))


# ── standing — GET reference + POST live analysis ────────────────────────────

@legal_router.get("/standing-analysis", response_class=HTMLResponse)
def standing_analysis_get(request: Request):
    return templates.TemplateResponse(
        request, "standing_analysis.html",
        context=_ctx(request, {"analysis": None, "analyzed": False}),
    )


@legal_router.post("/standing-analysis", response_class=HTMLResponse)
async def standing_analysis_post(
    request: Request,
    target_name: str = Form(""),
    what_happened: str = Form(""),
    financial_loss: float = Form(0.0),
    injury_claimed: bool = Form(False),
    complaint_id: str = Form("complaint-1"),
):
    intake_state = {
        "complaintProfile": {
            "complaints": [{
                "complaintId": complaint_id,
                "targetName": target_name,
                "whatHappened": what_happened,
                "financialLossAmount": financial_loss,
                "injuryClaimed": injury_claimed,
            }]
        }
    }
    analysis = _run_standing(intake_state, complaint_id)
    return templates.TemplateResponse(
        request, "standing_analysis.html",
        context=_ctx(request, {"analysis": analysis, "analyzed": True}),
    )


# ── capacity — GET reference + POST live analysis ────────────────────────────

@legal_router.get("/capacity-analysis", response_class=HTMLResponse)
def capacity_analysis_get(request: Request):
    return templates.TemplateResponse(
        request, "capacity_analysis.html",
        context=_ctx(request, {"analysis": None, "analyzed": False}),
    )


@legal_router.post("/capacity-analysis", response_class=HTMLResponse)
async def capacity_analysis_post(
    request: Request,
    target_name: str = Form(""),
    target_type: str = Form(""),
    target_person: str = Form(""),
    desired_outcome: str = Form(""),
    complaint_id: str = Form("complaint-1"),
):
    intake_state = {
        "complaintProfile": {
            "complaints": [{
                "complaintId": complaint_id,
                "targetName": target_name,
                "targetType": target_type,
                "targetPerson": target_person,
                "desiredOutcome": desired_outcome,
            }]
        }
    }
    analysis = _run_capacity(intake_state, complaint_id)
    return templates.TemplateResponse(
        request, "capacity_analysis.html",
        context=_ctx(request, {"analysis": analysis, "analyzed": True}),
    )
