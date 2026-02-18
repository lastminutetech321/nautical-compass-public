from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3

app = FastAPI()
templates = Jinja2Templates(directory="templates")
# ---------- DATABASE SETUP ----------

def init_db():
    conn = sqlite3.connect("intake.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS intake (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            service_requested TEXT NOT NULL,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- DATA MODEL ----------

class IntakeForm(BaseModel):
    name: str
    email: str
    service_requested: str
    notes: str | None = None

# ---------- ROUTES ----------

@app.get("/")
def root():
    return {"message": "Nautical Compass is live"}

@app.get("/intake")
def intake_info():
    return {"message": "Submit intake via POST request to /intake"}

@app.post("/intake")
def submit_intake(form: IntakeForm):
    conn = sqlite3.connect("intake.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO intake (name, email, service_requested, notes)
        VALUES (?, ?, ?, ?)
    """, (form.name, form.email, form.service_requested, form.notes))
    conn.commit()
    conn.close()

    return {"status": "Intake stored successfully"}

@app.get("/admin/intake")
def view_intake():
    conn = sqlite3.connect("intake.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM intake")
    rows = cursor.fetchall()
    conn.close()

    return {"entries": rows}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("favicon.png")

@app.get("/intake-form")
def intake_form(request: Request):
    return templates.TemplateResponse("intake_form.html", {"request": request})
