from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def page(request: Request, template: str, title: str):
    return templates.TemplateResponse(template, {"request": request, "title": title})


@router.get("/get_access")
def get_access_alias():
    return RedirectResponse(url="/get-access", status_code=307)


@router.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    return templates.TemplateResponse("dashboards.html", {"request": request})


@router.get("/avpt/request", response_class=HTMLResponse)
def avpt_request(request: Request):
    return templates.TemplateResponse("avpt_request.html", {"request": request})


@router.get("/lmt", response_class=HTMLResponse)
def lmt(request: Request):
    return templates.TemplateResponse("lmt_home.html", {"request": request})


@router.get("/lmt/worker", response_class=HTMLResponse)
def lmt_worker(request: Request):
    return templates.TemplateResponse("lmt_worker.html", {"request": request})


@router.get("/checkout/further_action")
def checkout_further_action():
    return {"status": "checkout further action route alive"}


@router.get("/intake", response_class=HTMLResponse)
def intake(request: Request):
    return templates.TemplateResponse("intake.html", {"request": request})


@router.get("/intake/company", response_class=HTMLResponse)
def intake_company(request: Request):
    return templates.TemplateResponse("intake_production.html", {"request": request})


@router.get("/intake/event", response_class=HTMLResponse)
def intake_event(request: Request):
    return templates.TemplateResponse("intake_form.html", {"request": request})


@router.get("/intake/logistics", response_class=HTMLResponse)
def intake_logistics(request: Request):
    return templates.TemplateResponse("intake_form.html", {"request": request})


@router.get("/intake/rental", response_class=HTMLResponse)
def intake_rental(request: Request):
    return templates.TemplateResponse("dash_rental.html", {"request": request})


@router.get("/intake/tech", response_class=HTMLResponse)
def intake_tech(request: Request):
    return templates.TemplateResponse("intake_labor.html", {"request": request})


@router.get("/admin/partners-dashboard", response_class=HTMLResponse)
def admin_partners_dashboard(request: Request):
    return templates.TemplateResponse("partners_dashboard.html", {"request": request})


@router.get("/admin/partners-export.csv")
def admin_partners_export():
    return "partner,status\nplaceholder,alive\n"
