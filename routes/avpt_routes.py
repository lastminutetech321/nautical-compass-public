import time
import sqlite3
import os
import logging
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")
avpt_router = APIRouter()

_DB_PATH = os.getenv("DB_PATH", "nautical_compass.db")


def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return ctx


def _get_avpt_rows() -> list:
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM avpt_requests ORDER BY id DESC LIMIT 100"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("avpt_requests table not available: %s", exc)
        return []


@avpt_router.get("/avpt")
def avpt_home(request: Request):
    return templates.TemplateResponse(request, "avpt_home.html", context=_ctx(request))


@avpt_router.get("/avpt/intake")
def avpt_intake(request: Request):
    return templates.TemplateResponse(request, "avpt_client_intake.html", context=_ctx(request))


@avpt_router.get("/avpt/dashboard")
def avpt_dashboard(request: Request):
    rows = _get_avpt_rows()
    return templates.TemplateResponse(
        request,
        "avpt_dashboard.html",
        context=_ctx(request, {"rows": rows}),
    )
