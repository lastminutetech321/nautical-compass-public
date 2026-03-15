from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import shutil
import time

app = FastAPI(title="Nautical Compass")

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def render(request: Request, template: str):
    return templates.TemplateResponse(template, {"request": request, "v": int(time.time())})


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "index.html")


@app.get("/hall", response_class=HTMLResponse)
def hall(request: Request):
    return render(request, "hall.html")


@app.get("/services", response_class=HTMLResponse)
def services(request: Request):
    return render(request, "services.html")


# ---------- CASE DOCK ----------

@app.get("/modules/case-dock", response_class=HTMLResponse)
def case_dock(request: Request):
    return render(request, "case_dock.html")


@app.post("/modules/case-dock")
async def case_dock_submit(
    name: str = Form(...),
    email: str = Form(...),
    case_summary: str = Form(...),
    documents: list[UploadFile] = File(...)
):
    for doc in documents:
        file_location = f"{UPLOAD_DIR}/{doc.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(doc.file, buffer)

    return RedirectResponse("/modules/signal-dock", status_code=303)


# ---------- SIGNAL DOCK ----------

@app.get("/modules/signal-dock", response_class=HTMLResponse)
def signal_dock(request: Request):
    return render(request, "signal_dock.html")


# ---------- EQUITY ENGINE ----------

@app.get("/modules/equity-engine", response_class=HTMLResponse)
def equity_engine(request: Request):
    return render(request, "equity_engine.html")


# ---------- NAVIGATOR AI ----------

@app.get("/modules/navigator-ai", response_class=HTMLResponse)
def navigator_ai(request: Request):
    return render(request, "navigator_ai.html")


# ---------- PRODUCTION INTAKE ----------

@app.get("/intake/production", response_class=HTMLResponse)
def intake_production(request: Request):
    return render(request, "intake_production.html")


@app.post("/intake/production")
async def production_submit(
    company: str = Form(...),
    contact: str = Form(...),
    event_location: str = Form(...),
    crew_needed: str = Form(...),
    documents: list[UploadFile] = File(...)
):
    for doc in documents:
        file_location = f"{UPLOAD_DIR}/{doc.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(doc.file, buffer)

    return RedirectResponse("/services", status_code=303)


# ---------- LABOR DISPATCH ----------

@app.get("/intake/labor", response_class=HTMLResponse)
def intake_labor(request: Request):
    return render(request, "intake_labor.html")


@app.post("/intake/labor")
async def labor_submit(
    name: str = Form(...),
    role: str = Form(...),
    availability: str = Form(...),
    resume: UploadFile = File(...)
):
    file_location = f"{UPLOAD_DIR}/{resume.filename}"
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(resume.file, buffer)

    return RedirectResponse("/services", status_code=303)


# ---------- PARTNER PORT ----------

@app.get("/partner", response_class=HTMLResponse)
def partner(request: Request):
    return render(request, "partner_intake.html")


@app.post("/partner")
async def partner_submit(
    company: str = Form(...),
    service_type: str = Form(...),
    territory: str = Form(...),
    documents: list[UploadFile] = File(...)
):
    for doc in documents:
        file_location = f"{UPLOAD_DIR}/{doc.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(doc.file, buffer)

    return RedirectResponse("/services", status_code=303)
