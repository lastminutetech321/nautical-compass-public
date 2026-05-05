import hmac
import os
import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _safe_next(url: str) -> str:
    """Allow only relative same-origin paths to prevent open-redirect."""
    if url and url.startswith("/") and not url.startswith("//"):
        return url
    return "/command-deck"


def _ctx(request: Request, extra: dict | None = None) -> dict:
    ctx: dict = {"request": request, "v": int(time.time())}
    if extra:
        ctx.update(extra)
    return ctx


@router.get("/operator/login", response_class=HTMLResponse)
def operator_login_page(request: Request):
    next_url = _safe_next(request.query_params.get("next", "/command-deck"))
    return templates.TemplateResponse(
        request,
        "operator_login.html",
        context=_ctx(request, {"error": None, "next": next_url}),
    )


@router.post("/operator/login")
async def operator_login(
    request: Request,
    passphrase: str = Form(...),
):
    next_url = _safe_next(request.query_params.get("next", "/command-deck"))
    admin_token = os.getenv("OPERATOR_ADMIN_TOKEN", "")
    coordinator_token = os.getenv("OPERATOR_COORDINATOR_TOKEN", "")

    role: str | None = None
    if admin_token and hmac.compare_digest(passphrase.strip(), admin_token):
        role = "admin"
    elif coordinator_token and hmac.compare_digest(passphrase.strip(), coordinator_token):
        role = "coordinator"

    if role:
        request.session["role"] = role
        request.session["login_ts"] = int(time.time())
        return RedirectResponse(next_url, status_code=302)

    return templates.TemplateResponse(
        request,
        "operator_login.html",
        context=_ctx(request, {"error": "Invalid passphrase.", "next": next_url}),
        status_code=401,
    )


@router.get("/operator/logout")
def operator_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/operator/login", status_code=302)
