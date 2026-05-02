import time
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from services.compliance_checklist_service import get_checklist_items

templates = Jinja2Templates(directory="templates")
operator_rail_router = APIRouter()


def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return ctx


@operator_rail_router.get("/operator-rail")
def operator_rail(request: Request):
    return templates.TemplateResponse(request, "operator_rail.html", context=_ctx(request))


@operator_rail_router.get("/operator-profile")
def operator_profile(request: Request):
    return templates.TemplateResponse(request, "operator_profile.html", context=_ctx(request))


@operator_rail_router.get("/captain-preview")
def captain_preview(request: Request):
    return templates.TemplateResponse(request, "captain_preview.html", context=_ctx(request))


@operator_rail_router.get("/compliance-checklist")
def compliance_checklist(request: Request, operator_type: str = "freelancer"):
    items = get_checklist_items(operator_type)
    return templates.TemplateResponse(
        request,
        "compliance_checklist.html",
        context=_ctx(request, {"items": items, "operator_type": operator_type}),
    )
