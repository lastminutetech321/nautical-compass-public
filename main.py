# --------------------
# Contributor Intake (DEEP EXTRACT + RAIL ASSIGNMENT)
# --------------------

from typing import Optional, List
from pydantic import BaseModel, EmailStr
from fastapi.responses import HTMLResponse, JSONResponse

# ---------- MODEL ----------
class ContributorForm(BaseModel):
    # Identity
    name: str
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    website: Optional[str] = None

    # Core fit
    contributor_type: str  # "operator" | "manufacturer" | "sponsor" | "builder" | "investor" | "advisor"
    primary_role: str      # e.g., "LED Manufacturer Rep", "AV Ops", "Legal Ops", "Sales", etc.

    # Geography + coverage
    home_region: str       # e.g., "DMV", "Northeast", "Southeast", "National", "Global"
    can_travel: str        # "No" | "Regional" | "National" | "International"
    coverage_regions: Optional[str] = None  # free text

    # Assets + capabilities
    assets: Optional[str] = None            # "LED wall inventory", "warehouse", "trucks", "capital", etc.
    specialties: Optional[str] = None       # list-like free text
    certifications: Optional[str] = None

    # Capacity + availability
    weekly_hours: str      # "0-5" | "5-10" | "10-20" | "20-40" | "40+"
    start_timeline: str    # "Now" | "1-2 weeks" | "30 days" | "60+"
    bandwidth_note: Optional[str] = None

    # Alignment + standards
    alignment: str         # mission alignment statement (dropdown)
    nonnegotiables: Optional[str] = None    # boundaries / constraints
    success_definition: Optional[str] = None

    # Deal + compensation preferences
    deal_preference: str   # "cash" | "revshare" | "equity" | "mixed" | "sponsor"
    budget_range: Optional[str] = None      # for sponsors/manufacturers

    # Proof
    portfolio_links: Optional[str] = None
    references: Optional[str] = None

    # Message
    message: Optional[str] = None


# ---------- DB TABLE ----------
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

            score INTEGER NOT NULL DEFAULT 0,
            rail TEXT NOT NULL DEFAULT 'triage',
            status TEXT NOT NULL DEFAULT 'new',

            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Call it once during startup/init
init_contributors_table()


# ---------- SCORING + RAILS ----------
def _score_contributor(f: ContributorForm) -> int:
    score = 0

    # Type priority (you can tune this)
    type_weights = {
        "operator": 20,
        "manufacturer": 18,
        "sponsor": 16,
        "builder": 14,
        "investor": 16,
        "advisor": 10
    }
    score += type_weights.get(f.contributor_type.lower().strip(), 8)

    # Timeline
    timeline_weights = {"now": 18, "1-2 weeks": 14, "30 days": 10, "60+": 6}
    score += timeline_weights.get(f.start_timeline.lower().strip(), 6)

    # Weekly hours
    hours_weights = {"0-5": 4, "5-10": 8, "10-20": 12, "20-40": 16, "40+": 18}
    score += hours_weights.get(f.weekly_hours.strip(), 6)

    # Travel capability
    travel_weights = {"no": 0, "regional": 6, "national": 10, "international": 12}
    score += travel_weights.get(f.can_travel.lower().strip(), 4)

    # Assets / proof signals
    if f.assets and len(f.assets.strip()) > 10:
        score += 10
    if f.portfolio_links and len(f.portfolio_links.strip()) > 8:
        score += 10
    if f.website and len(f.website.strip()) > 6:
        score += 6
    if f.references and len(f.references.strip()) > 6:
        score += 6

    # Alignment
    alignment_bonus = {
        "mission-first": 10,
        "balanced": 6,
        "profit-first": 2
    }
    score += alignment_bonus.get(f.alignment.lower().strip(), 4)

    return int(score)


def _assign_rail(f: ContributorForm, score: int) -> str:
    t = f.contributor_type.lower().strip()

    # High-fit routing
    if score >= 70:
        if t == "manufacturer":
            return "hardware_supply"
        if t == "sponsor":
            return "sponsorship"
        if t == "operator":
            return "ops_build"
        if t == "investor":
            return "capital"
        if t == "builder":
            return "infrastructure"
        return "priority"

    # Mid-fit routing
    if score >= 45:
        if t in ("manufacturer", "sponsor"):
            return "bd_followup"
        if t == "operator":
            return "ops_pool"
        return "review"

    # Low-fit / unclear
    return "triage"


# ---------- ROUTES ----------
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
        score, rail, "new",
        now_iso()
    ))
    conn.commit()
    conn.close()

    # Return BOTH: user-friendly and system-friendly
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
