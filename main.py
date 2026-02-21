# --------------------
# Contributor Intake (Fit Discovery + Rails)
# --------------------

from typing import Optional
from pydantic import BaseModel, EmailStr
from fastapi.responses import HTMLResponse, JSONResponse

class ContributorForm(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    website: Optional[str] = None

    contributor_type: str
    primary_role: str

    home_region: str
    can_travel: str
    coverage_regions: Optional[str] = None

    assets: Optional[str] = None
    specialties: Optional[str] = None
    certifications: Optional[str] = None

    weekly_hours: str
    start_timeline: str
    bandwidth_note: Optional[str] = None

    alignment: str
    nonnegotiables: Optional[str] = None
    success_definition: Optional[str] = None

    deal_preference: str
    budget_range: Optional[str] = None

    portfolio_links: Optional[str] = None
    references: Optional[str] = None

    message: Optional[str] = None

    # Optional quick-fit (if template sends it)
    primary_interest: Optional[str] = None


def init_contributors_table():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            company TEXT,
            website TEXT,

            contributor_type TEXT NOT NULL,
            primary_role TEXT NOT NULL,

            home_region TEXT NOT NULL,
            can_travel TEXT NOT NULL,
            coverage_regions TEXT,

            assets TEXT,
            specialties TEXT,
            certifications TEXT,

            weekly_hours TEXT NOT NULL,
            start_timeline TEXT NOT NULL,
            bandwidth_note TEXT,

            alignment TEXT NOT NULL,
            nonnegotiables TEXT,
            success_definition TEXT,

            deal_preference TEXT NOT NULL,
            budget_range TEXT,

            portfolio_links TEXT,
            references TEXT,

            message TEXT,

            primary_interest TEXT,

            score INTEGER NOT NULL DEFAULT 0,
            rail TEXT NOT NULL DEFAULT 'triage',
            status TEXT NOT NULL DEFAULT 'new',

            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_contributors_table()


def _score_contributor(f: ContributorForm) -> int:
    score = 0

    t = (f.contributor_type or "").lower().strip()
    type_weights = {
        "builder": 18,
        "operator": 16,
        "manufacturer": 18,
        "sponsor": 16,
        "investor": 16,
        "advisor": 10
    }
    score += type_weights.get(t, 10)

    # If they said "unknown / route me", do NOT penalize
    pi = (f.primary_interest or "").lower().strip()
    if pi in ("unknown", ""):
        score += 6
    elif pi in ("build", "infra", "hardware", "sponsor", "capital", "advice"):
        score += 8

    timeline_weights = {"now": 18, "1-2 weeks": 14, "30 days": 10, "60+": 6}
    score += timeline_weights.get((f.start_timeline or "").lower().strip(), 6)

    hours_weights = {"0-5": 4, "5-10": 8, "10-20": 12, "20-40": 16, "40+": 18}
    score += hours_weights.get((f.weekly_hours or "").strip(), 6)

    travel_weights = {"no": 0, "regional": 6, "national": 10, "international": 12}
    score += travel_weights.get((f.can_travel or "").lower().strip(), 4)

    if f.assets and len(f.assets.strip()) > 10:
        score += 10
    if f.portfolio_links and len(f.portfolio_links.strip()) > 8:
        score += 10
    if f.website and len(f.website.strip()) > 6:
        score += 6
    if f.references and len(f.references.strip()) > 6:
        score += 6

    alignment_bonus = {"mission-first": 10, "balanced": 6, "profit-first": 2}
    score += alignment_bonus.get((f.alignment or "").lower().strip(), 4)

    return int(score)


def _assign_rail(f: ContributorForm, score: int) -> str:
    t = (f.contributor_type or "").lower().strip()
    pi = (f.primary_interest or "").lower().strip()

    # Priority routing
    if score >= 70:
        if t == "manufacturer" or pi == "hardware":
            return "hardware_supply"
        if t == "sponsor" or pi == "sponsor":
            return "sponsorship"
        if t in ("builder", "operator") or pi == "build":
            return "builders_core"
        if t == "investor" or pi == "capital":
            return "capital"
        if pi == "infra":
            return "infrastructure"
        return "priority"

    # Mid-fit routing
    if score >= 45:
        if t in ("manufacturer", "sponsor"):
            return "bd_followup"
        if t in ("builder", "operator"):
            return "builders_pool"
        if t == "investor":
            return "capital_review"
        return "review"

    return "triage"


@app.get("/contributor", response_class=HTMLResponse)
def contributor_page(request: Request):
    return templates.TemplateResponse("contributor_intake.html", {"request": request})


@app.post("/contributor")
def submit_contributor(form: ContributorForm):
    score = _score_contributor(form)
    rail = _assign_rail(form, score)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contributors (
            name, email, phone, company, website,
            contributor_type, primary_role,
            home_region, can_travel, coverage_regions,
            assets, specialties, certifications,
            weekly_hours, start_timeline, bandwidth_note,
            alignment, nonnegotiables, success_definition,
            deal_preference, budget_range,
            portfolio_links, references,
            message,
            primary_interest,
            score, rail, status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?,
                ?,
                ?, ?, ?,
                ?)
    """, (
        form.name, str(form.email), form.phone, form.company, form.website,
        form.contributor_type, form.primary_role,
        form.home_region, form.can_travel, form.coverage_regions,
        form.assets, form.specialties, form.certifications,
        form.weekly_hours, form.start_timeline, form.bandwidth_note,
        form.alignment, form.nonnegotiables, form.success_definition,
        form.deal_preference, form.budget_range,
        form.portfolio_links, form.references,
        form.message,
        form.primary_interest,
        score, rail, "new",
        now_iso()
    ))
    conn.commit()
    conn.close()

    return JSONResponse({
        "status": "Contributor submission received",
        "rail_assigned": rail,
        "score": score
    })


@app.get("/admin/contributors")
def admin_contributors():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM contributors ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"entries": rows}
