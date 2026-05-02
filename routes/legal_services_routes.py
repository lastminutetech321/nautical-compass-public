import time
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
legal_router = APIRouter()


def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return ctx


@legal_router.get("/legal-services")
def legal_services_hub(request: Request):
    return templates.TemplateResponse(request, "legal_services.html", context=_ctx(request))


@legal_router.get("/standing-analysis")
def standing_analysis_page(request: Request):
    return templates.TemplateResponse(request, "standing_analysis.html", context=_ctx(request))


@legal_router.get("/capacity-analysis")
def capacity_analysis_page(request: Request):
    return templates.TemplateResponse(request, "capacity_analysis.html", context=_ctx(request))


@legal_router.get("/section-1983")
def section_1983_page(request: Request):
    return templates.TemplateResponse(request, "section_1983.html", context=_ctx(request))


@legal_router.get("/consumer-rights")
def consumer_rights_page(request: Request):
    return templates.TemplateResponse(request, "consumer_rights.html", context=_ctx(request))


@legal_router.get("/status-correction")
def status_correction_page(request: Request):
    return templates.TemplateResponse(request, "status_correction.html", context=_ctx(request))
