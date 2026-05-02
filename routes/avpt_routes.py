import time
import sqlite3
import os
import logging

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.twilio_adapter import is_twilio_configured

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")
avpt_router = APIRouter()

_DB_PATH = os.getenv("DB_PATH", "nautical_compass.db")


def _ctx(request: Request, data: dict = None) -> dict:
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    ctx["sms_connected"] = is_twilio_configured()
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


def _store_avpt_request(data: dict) -> bool:
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS avpt_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_name TEXT,
                contact_name TEXT,
                email TEXT,
                city TEXT,
                date_start TEXT,
                date_end TEXT,
                created_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO avpt_requests (org_name, contact_name, email, city, date_start, date_end, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                data.get("org_name", ""),
                data.get("contact_name", ""),
                data.get("email", ""),
                data.get("city", ""),
                data.get("date_start", ""),
                data.get("date_end", ""),
                data.get("created_at", ""),
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        logger.warning("avpt_requests store failed: %s", exc)
        return False


@avpt_router.get("/avpt", response_class=HTMLResponse)
def avpt_home(request: Request):
    return templates.TemplateResponse(request, "avpt_home.html", context=_ctx(request))


@avpt_router.get("/avpt/intake", response_class=HTMLResponse)
def avpt_intake(request: Request):
    return templates.TemplateResponse(request, "avpt_client_intake.html", context=_ctx(request))


@avpt_router.post("/avpt/intake", response_class=HTMLResponse)
async def avpt_intake_submit(
    request: Request,
    company_name: str = Form(""),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    city: str = Form(""),
    date_start: str = Form(""),
    date_end: str = Form(""),
):
    from datetime import datetime, timezone
    _store_avpt_request({
        "org_name": company_name,
        "contact_name": contact_name,
        "email": contact_email,
        "city": city,
        "date_start": date_start,
        "date_end": date_end,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return templates.TemplateResponse(
        request,
        "avpt_thanks.html",
        context=_ctx(request, {"contact_name": contact_name, "company_name": company_name}),
    )


@avpt_router.get("/avpt/request", response_class=HTMLResponse)
def avpt_request(request: Request):
    return templates.TemplateResponse(request, "avpt_request.html", context=_ctx(request))


@avpt_router.get("/avpt/results", response_class=HTMLResponse)
def avpt_results(request: Request):
    return templates.TemplateResponse(request, "avpt_results.html", context=_ctx(request))


@avpt_router.get("/avpt/dashboard", response_class=HTMLResponse)
def avpt_dashboard(request: Request):
    rows = _get_avpt_rows()
    return templates.TemplateResponse(
        request,
        "avpt_dashboard.html",
        context=_ctx(request, {"rows": rows}),
    )
