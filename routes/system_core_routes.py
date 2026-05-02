from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/compass", response_class=HTMLResponse)
def compass(request: Request):
    return templates.TemplateResponse("compass.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/dash/labor", response_class=HTMLResponse)
def dash_labor(request: Request):
    return templates.TemplateResponse("dash_labor.html", {"request": request})


@router.get("/dash/production", response_class=HTMLResponse)
def dash_production(request: Request):
    return templates.TemplateResponse("dash_production.html", {"request": request})


@router.get("/get-access", response_class=HTMLResponse)
def get_access(request: Request):
    return templates.TemplateResponse("get_access.html", {"request": request})


@router.get("/contributor", response_class=HTMLResponse)
def contributor(request: Request):
    return templates.TemplateResponse("contributor.html", {"request": request})
