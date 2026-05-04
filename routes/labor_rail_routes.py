import os
import time

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from services.living_ledger import log_page_view

templates = Jinja2Templates(directory="templates")
labor_rail_router = APIRouter()


def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return ctx


@labor_rail_router.get("/labor-rail")
def labor_rail(request: Request):
    log_page_view(request, rail="labor", event_type="labor_rail_page_viewed",
                  title="Labor Rail page viewed",
                  next_action="labor_rail_access_viewed",
                  residual_trigger="no_job_activity_after_signup")
    return templates.TemplateResponse(request, "labor_rail.html", context=_ctx(request))


@labor_rail_router.get("/labor-rail/access")
def labor_rail_access(request: Request):
    log_page_view(request, rail="labor", event_type="labor_rail_access_viewed",
                  title="Labor Rail access page viewed",
                  next_action="intake_form_opened")
    basic_link = os.getenv("STRIPE_LINK_LABOR_RAIL_BASIC", "").strip()
    pro_link = os.getenv("STRIPE_LINK_LABOR_RAIL_PRO", "").strip()
    return templates.TemplateResponse(
        request,
        "labor_rail_access.html",
        context=_ctx(request, {
            "labor_rail_basic": basic_link,
            "labor_rail_pro": pro_link,
        }),
    )
