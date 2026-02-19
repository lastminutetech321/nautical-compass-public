import os
import sqlite3
import smtplib
from email.message import EmailMessage
from pathlib import Path

import stripe
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="Nautical Compass Intake")

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DB_PATH = BASE_DIR / "intake.db"

# --- Static + Templates ---
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --- Stripe env ---
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
SUCCESS_URL = os.getenv("SUCCESS_URL")
CANCEL_URL = os.getenv("CANCEL_URL")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


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
    return FileResponse(str(STATIC_DIR / "favicon.ico"), media_type="image/x-icon")


@app.get("/intake-form", response_class=HTMLResponse)
def intake_form(request: Request):
    return templates.TemplateResponse("intake_form.html", {"request": request})


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

    # Optional email (only if env vars exist)
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

    return JSONResponse({"status": "Intake stored"})


@app.get("/admin/intake")
def view_intake():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, service_requested, notes FROM intake ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    return {"entries": [
        {"id": r[0], "name": r[1], "email": r[2], "service_requested": r[3], "notes": r[4]}
        for r in rows
    ]}


# ---------- STRIPE CHECKOUT ----------
@app.get("/checkout")
def checkout():
    # Hard stop if env vars missing
    missing = []
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_PRICE_ID:
        missing.append("STRIPE_PRICE_ID")
    if not SUCCESS_URL:
        missing.append("SUCCESS_URL")
    if not CANCEL_URL:
        missing.append("CANCEL_URL")

    if missing:
        return JSONResponse(
            {"error": "Missing environment variables", "missing": missing},
            status_code=500
        )

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
        )
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/success", response_class=HTMLResponse)
def success():
    return HTMLResponse("""
    <html><body style="font-family: system-ui; padding: 30px;">
      <h2>✅ Payment successful</h2>
      <p>You’re subscribed. You can now return to the site.</p>
      <p><a href="/intake-form">Back to Intake Form</a></p>
    </body></html>
    """)


@app.get("/cancel", response_class=HTMLResponse)
def cancel():
    return HTMLResponse("""
    <html><body style="font-family: system-ui; padding: 30px;">
      <h2>⚠ Checkout cancelled</h2>
      <p>No payment was made.</p>
      <p><a href="/intake-form">Back to Intake Form</a></p>
    </body></html>
    """) 
