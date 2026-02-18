import smtplib
from email.message import EmailMessage
import os                                      
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

    # ---------- EMAIL NOTIFICATION ----------
    try:
        msg = EmailMessage()
        msg["Subject"] = "New Intake Submission"
        msg["From"] = os.getenv("EMAIL_USER")
        msg["To"] = os.getenv("EMAIL_USER")

        msg.set_content(f"""
Name: {form.name}
Email: {form.email}
Service: {form.service_requested}
Notes: {form.notes}
""")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
            smtp.send_message(msg)

    except Exception as e:
        print("Email failed:", e)

    return {"status": "Intake stored and email attempted"}
    

@app.get("/admin/intake")
def view_intake():
    conn = sqlite3.connect("intake.db")
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
            "notes": row[4]
        })

    return {"entries": formatted}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("favicon.png")

@app.get("/intake-form")
def intake_form(request: Request):
    return templates.TemplateResponse("intake_form.html", {"request": request})
