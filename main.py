from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import time

app = FastAPI(title="Nautical Compass")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def render(request: Request, template: str, data=None):
    ctx = data or {}
    ctx["request"] = request
    ctx["v"] = int(time.time())
    return templates.TemplateResponse(template, ctx)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "index.html")


@app.get("/hall", response_class=HTMLResponse)
def hall(request: Request):
    return render(request, "hall.html")


@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return render(request, "services.html")


@app.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request):
    return render(request, "dashboards_hub.html")


@app.get("/lead", response_class=HTMLResponse)
def lead(request: Request):
    return render(request, "lead_intake.html")


@app.post("/lead")
def lead_submit(
    name: str = Form(""),
    email: str = Form(""),
    message: str = Form("")
):
    return RedirectResponse("/lead/thanks", status_code=303)


@app.get("/lead/thanks", response_class=HTMLResponse)
def lead_thanks(request: Request):
    return render(request, "lead_thanks.html")


@app.get("/partner", response_class=HTMLResponse)
def partner(request: Request):
    return render(request, "partner_intake.html")


@app.get("/sponsor", response_class=HTMLResponse)
def sponsor(request: Request):
    return render(request, "sponsor.html")


@app.get("/intake/production", response_class=HTMLResponse)
def intake_production(request: Request):
    return render(request, "intake_production.html")


@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor(request: Request):
    return render(request, "intake_labor.html")


@app.get("/checkout")
def checkout():
    return JSONResponse({"ok": True, "message": "Checkout placeholder active."})
