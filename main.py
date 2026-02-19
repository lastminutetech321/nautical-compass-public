import os
import sqlite3
import smtplib
from email.message import EmailMessage

from fastapi.responses import HTMLResponse
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="Nautical Compass intake")
app.mount("/static", StaticFiles(directory="static"), name="static")

# IMPORTANT:
# If your file is at templates/templates/intake_form.html then use this:
templates = Jinja2Templates(directory="templates")
# If you move the file to templates/intake_form.html then change to:
# templates = Jinja2Templates(directory="templates")

DB_PATH = "intake.db"

# ---------- DATABASE SETUP ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
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

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("static/favicon.ico", media_type="image/x-icon")

@app.get("/intake-form", response_class=HTMLResponse)
def intake_form():
    try:
        html = Path("templates/templates/intake_form.html").read_text(encoding="utf-8")
        return HTMLResponse(html)
    except FileNotFoundError:
        return HTMLResponse(
            "Template not found at templates/templates/intake_form.html. "
            "Check the filename and folder path.",
            status_code=500
        )

@app.get("/intake")
def intake_info():
    return {"message": "Submit intake via POST request to /intake"}

@app.post("/intake")
def submit_intake(form: IntakeForm):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO intake (name, email, service_requested, notes)
        VALUES (?, ?, ?, ?)
    """, (form.name, form.email, form.service_requested, form.notes))
    conn.commit()
    conn.close()

    # Email (only if env vars exist)
    try:
        email_user = os.getenv("EMAIL_USER")
        email_pass = os.getenv("EMAIL_PASS")

        if email_user and email_pass:
            msg = EmailMessage()
            msg["Subject"] = "New Intake Submission"
            msg["From"] = email_user
            msg["To"] = email_user
            msg.set_content(
                f"Name: {form.name}\n"
                f"Email: {form.email}\n"
                f"Service: {form.service_requested}\n"
                f"Notes: {form.notes}"
            )

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(email_user, email_pass)
                smtp.send_message(msg)

    except Exception as e:
        print("Email failed:", e)

    return {"status": "Intake stored"}

@app.get("/admin/intake")
def view_intake():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, service_requested, notes FROM intake")
    rows = cursor.fetchall()
    conn.close()

    formatted = []
    for row in rows:
        formatted.append({
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "service_requested": row[3],
            "notes": row[4],
        })

    return {"entries": formatted} 
