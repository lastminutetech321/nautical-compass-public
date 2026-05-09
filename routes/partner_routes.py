from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uuid
import time

templates = Jinja2Templates(directory="templates")

partner_router = APIRouter()

@partner_router.get("/partner/intake", response_class=HTMLResponse)
def partner_form(request: Request):
    return templates.TemplateResponse("partner_intake.html", {"request": request})


@partner_router.post("/partner/intake")
def partner_submit(
    request: Request,
    company_name: str = Form(None),
    contact_name: str = Form(None),
    contact_email: str = Form(None),
    app_type: str = Form(None),
    integration_needs: str = Form(None),
    revenue_model: str = Form(None),
    white_label: str = Form(None)
):
    submission = {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time()),
        "company": company_name,
        "contact": contact_name,
        "email": contact_email,
        "app_type": app_type,
        "integration": integration_needs,
        "revenue": revenue_model,
        "white_label": white_label
    }

    # TEMP: log to console (we upgrade later)
    print("PARTNER SUBMISSION:", submission)

    return {"status": "received", "id": submission["id"]}
