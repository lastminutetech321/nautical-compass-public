# render_helper.py
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")


def render(request: Request, template: str, data: dict = None) -> HTMLResponse:
    ctx = data or {}
    ctx["request"] = request
    return templates.TemplateResponse(template, ctx)
