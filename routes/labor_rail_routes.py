import os
import time

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
labor_rail_router = APIRouter()


def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return ctx


@labor_rail_router.get("/labor-rail")
def labor_rail(request: Request):
    return templates.TemplateResponse(request, "labor_rail.html", context=_ctx(request))


@labor_rail_router.get("/labor-rail/access")
def labor_rail_access(request: Request):
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
