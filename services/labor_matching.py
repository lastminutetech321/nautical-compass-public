"""
Labor Matching — Phase 1 + Phase 2.

Data sources (read-only):
  runtime/career_dna_ledger.jsonl    — primary: labor_profile_submitted events
  runtime/intake_submissions.jsonl   — secondary: intake_type=="labor" records

Write (append-only):
  runtime/labor_job_requests.jsonl   — one structured job per line (Phase 2)

Privacy rules enforced here:
  - No email, phone, exact address, or raw notes exposed in returned dicts
  - Worker identity shown only as a shortened display token
  - Job request notes are never written to JSONL
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from uuid import uuid4

CAREER_DNA_PATH         = Path("runtime/career_dna_ledger.jsonl")
INTAKE_SUBS_PATH        = Path("runtime/intake_submissions.jsonl")
JOB_REQUESTS_PATH       = Path("runtime/labor_job_requests.jsonl")
DISPATCH_ASSIGNMENTS_PATH = Path("runtime/labor_dispatch_assignments.jsonl")

MIN_READINESS_SCORE = 30   # pool view: profiles below this are hidden
MIN_JOB_MATCH_SCORE = 20   # job view: candidates below this are hidden


# ---------------------------------------------------------------------------
# Cert / skill helpers
# ---------------------------------------------------------------------------

def parse_cert_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [c.strip() for c in re.split(r"[,;|]", raw) if c.strip()]


def detect_skill_flags(cert_tags: list[str]) -> list[str]:
    joined = " ".join(cert_tags).lower()
    checks = [
        ("OSHA",      ["osha"]),
        ("Forklift",  ["forklift"]),
        ("Rigging",   ["rigging", "rig"]),
        ("Lift Cert", ["lift cert", "aerial", "scissor lift"]),
        ("ETCP",      ["etcp"]),
        ("CDL",       ["cdl"]),
        ("Audio",     ["audio", "a1", "a2"]),
        ("Video",     ["video", "v1", "v2"]),
        ("Lighting",  ["lighting", "lx", "l1", "l2"]),
        ("Stagehand", ["stagehand"]),
    ]
    return [label for label, needles in checks if any(n in joined for n in needles)]


def normalize_readiness(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in ("available immediately", "immediately", "within_1_week",
               "available within 1 week"):
        return "ready"
    if raw in ("within_2_weeks", "available within 2 weeks",
               "specific_dates", "specific dates only"):
        return "limited"
    if raw == "unavailable":
        return "unavailable"
    return "unknown"


# ---------------------------------------------------------------------------
# Profile scoring — 6-dimension model, max 100
#
#  Dimension          Max pts
#  ─────────────────  ───────
#  Role               30
#  Market             20
#  Availability       20   (ready=20, limited=10, else=0)
#  Certifications     15   (any cert tag or skill flag present)
#  Transport          10   (transport field truthy)
#  Verification src    5   (career_dna source = verified intake)
# ---------------------------------------------------------------------------

def score_worker_profile(worker: dict) -> int:
    """Return 0-100 readiness score using the 30/20/20/15/10/5 model."""
    score = 0

    if worker.get("role"):
        score += 30

    if worker.get("market"):
        score += 20

    readiness = normalize_readiness(worker.get("availability"))
    if readiness == "ready":
        score += 20
    elif readiness == "limited":
        score += 10

    if worker.get("cert_tags") or worker.get("skill_flags"):
        score += 15

    transport = (worker.get("transport") or "").strip().lower()
    if transport and transport not in ("no", "none", "false", "0"):
        score += 10

    if worker.get("source") == "career_dna":
        score += 5

    return min(score, 100)


# ---------------------------------------------------------------------------
# Role / market filter matching
# ---------------------------------------------------------------------------

def _role_matches(worker_role: str, filter_role: str) -> bool:
    if not filter_role:
        return True
    wr = worker_role.lower()
    fr = filter_role.lower().replace("-", "_").replace(" ", "_")
    return fr in wr or wr in fr or any(
        part in wr for part in fr.split("_") if len(part) > 2
    )


def _market_matches(worker_market: str, filter_market: str) -> bool:
    if not filter_market:
        return True
    wm = worker_market.lower()
    fm = filter_market.lower()
    return any(word in wm for word in fm.split() if len(word) > 2) or \
           any(word in fm for word in wm.split() if len(word) > 2)


# ---------------------------------------------------------------------------
# Load workers from career_dna_ledger.jsonl
# ---------------------------------------------------------------------------

def _load_from_career_dna() -> dict[str, dict]:
    """
    Read career_dna_ledger.jsonl, keep only labor_profile_submitted events,
    deduplicate by worker_id keeping the latest entry per worker.
    Returns {worker_id: profile_dict}.
    """
    if not CAREER_DNA_PATH.exists():
        return {}

    workers: dict[str, dict] = {}
    try:
        lines = CAREER_DNA_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        if entry.get("event_type") != "labor_profile_submitted":
            continue

        worker_id = entry.get("worker_id") or ""
        if not worker_id:
            continue

        payload = entry.get("payload") or {}
        cert_list = entry.get("certifications") or []
        cert_raw = ", ".join(cert_list) if isinstance(cert_list, list) else str(cert_list)

        profile = {
            "worker_id":    worker_id,
            "source":       "career_dna",
            "role":         entry.get("role") or "",
            "market":       entry.get("market") or "",
            "availability": payload.get("availability") or "",
            "transport":    payload.get("transport") or "",
            "cert_raw":     cert_raw,
            "cert_tags":    cert_list if isinstance(cert_list, list) else parse_cert_tags(cert_raw),
            "ts":           entry.get("ts", 0),
        }
        # Always overwrite with the newer entry (lines are append-only)
        workers[worker_id] = profile

    return workers


# ---------------------------------------------------------------------------
# Load workers from intake_submissions.jsonl (labor intake_type only)
# ---------------------------------------------------------------------------

def _load_from_intake_subs() -> dict[str, dict]:
    """
    Read intake_submissions.jsonl for intake_type=="labor" records.
    Returns {worker_id_or_intake_id: profile_dict}.
    """
    if not INTAKE_SUBS_PATH.exists():
        return {}

    workers: dict[str, dict] = {}
    try:
        lines = INTAKE_SUBS_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        if (entry.get("intake_type") or "").lower() not in ("labor", "production"):
            continue

        worker_id = entry.get("nc_worker_id") or entry.get("intake_id") or ""
        if not worker_id:
            continue

        desc = entry.get("description") or entry.get("subject") or ""
        cert_raw = entry.get("certifications") or ""
        cert_tags = parse_cert_tags(cert_raw) or parse_cert_tags(desc)

        profile = {
            "worker_id":    worker_id,
            "source":       "intake_subs",
            "role":         entry.get("primary_role") or entry.get("intake_type") or "",
            "market":       entry.get("market_area") or entry.get("location") or "",
            "availability": entry.get("availability") or "",
            "transport":    entry.get("transport") or "",
            "cert_raw":     cert_raw,
            "cert_tags":    cert_tags,
            "ts":           entry.get("created_at") or entry.get("ts") or 0,
        }
        workers[worker_id] = profile

    return workers


# ---------------------------------------------------------------------------
# Build display token — no PII, just a short opaque label
# ---------------------------------------------------------------------------

def _display_token(worker_id: str) -> str:
    """Return a short display token safe for public rendering."""
    if worker_id.startswith("wrk_"):
        return "WRK-" + worker_id[4:10].upper()
    return "WRK-" + worker_id[:6].upper()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_match_pool(
    role_filter: str = "",
    market_filter: str = "",
) -> list[dict]:
    """
    Return ranked worker profiles from all available JSONL sources.

    Applies:
      - Deduplication (career_dna wins over intake_subs for the same worker_id)
      - PII stripping (no email, phone, exact address, raw notes)
      - Minimum readiness filter (score < MIN_READINESS_SCORE → hidden)
      - Optional role / market filter
      - Descending sort by readiness score
    """
    career_workers = _load_from_career_dna()
    intake_workers = _load_from_intake_subs()

    # Merge: career_dna takes precedence
    merged: dict[str, dict] = {**intake_workers, **career_workers}

    pool = []
    for profile in merged.values():
        cert_tags   = profile.get("cert_tags") or parse_cert_tags(profile.get("cert_raw"))
        skill_flags = detect_skill_flags(cert_tags)
        readiness   = normalize_readiness(profile.get("availability"))

        profile["cert_tags"]   = cert_tags
        profile["skill_flags"] = skill_flags
        profile["readiness"]   = readiness

        score = score_worker_profile(profile)
        if score < MIN_READINESS_SCORE:
            continue

        # Apply filters
        if role_filter and not _role_matches(profile.get("role") or "", role_filter):
            continue
        if market_filter and not _market_matches(profile.get("market") or "", market_filter):
            continue

        pool.append({
            "display_id":   _display_token(profile["worker_id"]),
            "role":         profile.get("role") or "",
            "market":       profile.get("market") or "",
            "readiness":    readiness,
            "score":        score,
            "skill_flags":  skill_flags,
            "cert_count":   len(cert_tags),
            # Fairness placeholder — no actual rate exposed in Phase 1
            "rate_band":    "Market Rate",
        })

    pool.sort(key=lambda w: w["score"], reverse=True)
    return pool


# ---------------------------------------------------------------------------
# Readiness score breakdown — 6-dimension detail for a single worker
# ---------------------------------------------------------------------------

DIMENSIONS = [
    ("role",         "Role",              30, "Primary role or trade is on file"),
    ("market",       "Market",            20, "Service area or city is specified"),
    ("availability", "Availability",      20, "Dispatch availability is set"),
    ("certs",        "Certifications",    15, "At least one credential or skill flag"),
    ("transport",    "Transport",         10, "Transport capability confirmed"),
    ("source",       "Verified Source",    5, "Profile submitted through verified intake"),
]


def get_worker_readiness_breakdown(worker_id: str | None = None, cert_strictness: str = "normal") -> dict:
    """
    Return a 6-dimension readiness breakdown for a single worker.
    If worker_id is None, uses the latest labor_profile_submitted entry
    from career_dna_ledger.jsonl.

    Returns a dict with:
      worker_id, display_id, total_score, dimensions (list of dim dicts),
      missing_steps (list of improvement tips)
    """
    career = _load_from_career_dna()
    intake = _load_from_intake_subs()
    merged = {**intake, **career}

    profile: dict | None = None
    if worker_id and worker_id in merged:
        profile = merged[worker_id]
    elif merged:
        # Latest by ts
        profile = max(merged.values(), key=lambda p: p.get("ts", 0))

    if not profile:
        return {
            "worker_id":    None,
            "display_id":   None,
            "total_score":  0,
            "dimensions":   [],
            "missing_steps": ["No worker profile found. Submit a labor intake to begin."],
        }

    cert_tags   = profile.get("cert_tags") or parse_cert_tags(profile.get("cert_raw", ""))
    skill_flags = detect_skill_flags(cert_tags)
    readiness   = normalize_readiness(profile.get("availability"))
    transport   = (profile.get("transport") or "").strip().lower()

    _cert_pts_map = {"low": 5, "normal": 15, "high": 20}
    cert_pts = _cert_pts_map.get(cert_strictness, 15)

    earned = {
        "role":         30 if profile.get("role") else 0,
        "market":       20 if profile.get("market") else 0,
        "availability": 20 if readiness == "ready" else (10 if readiness == "limited" else 0),
        "certs":        cert_pts if (cert_tags or skill_flags) else 0,
        "transport":    10 if (transport and transport not in ("no", "none", "false", "0")) else 0,
        "source":        5 if profile.get("source") == "career_dna" else 0,
    }

    dims = []
    missing_steps = []
    for key, label, max_pts, tip in DIMENSIONS:
        pts = earned[key]
        effective_max = cert_pts if key == "certs" else max_pts
        dims.append({
            "key":     key,
            "label":   label,
            "earned":  min(pts, effective_max),
            "max":     effective_max,
            "filled":  pts > 0,
        })
        if pts == 0:
            missing_steps.append(tip)

    total = sum(earned.values())
    return {
        "worker_id":     profile.get("worker_id"),
        "display_id":    _display_token(profile.get("worker_id", "unknown")),
        "total_score":   min(total, 100),
        "dimensions":    dims,
        "missing_steps": missing_steps,
        "role":          profile.get("role") or "",
        "market":        profile.get("market") or "",
        "readiness":     readiness,
        "skill_flags":   skill_flags,
        "cert_count":    len(cert_tags),
    }


# ---------------------------------------------------------------------------
# Company dispatch directory — sanitized, no contact PII
# ---------------------------------------------------------------------------

COMPANY_DIRECTORY_PATH = Path("runtime/company_directory.json")

# Fields safe to expose in the worker-facing dispatch directory
_SAFE_COMPANY_FIELDS = {"name", "city", "state", "company_type", "status",
                        "market", "dispatch_active", "roles_dispatched", "notes_public"}


def get_dispatch_companies(city_filter: str = "", status_filter: str = "") -> list[dict]:
    """
    Return a sanitized list of companies from company_directory.json.
    Strips all contact fields (email, phone, address, contact_name, etc.).
    Returns only fields in _SAFE_COMPANY_FIELDS.
    """
    if not COMPANY_DIRECTORY_PATH.exists():
        return []

    try:
        raw = json.loads(COMPANY_DIRECTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(raw, list):
        raw = []

    companies = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue

        safe = {k: v for k, v in entry.items() if k in _SAFE_COMPANY_FIELDS}
        # Ensure required display fields have defaults
        safe.setdefault("name", "Unknown Company")
        safe.setdefault("city", "")
        safe.setdefault("state", "")
        safe.setdefault("company_type", "")
        safe.setdefault("status", "")
        safe.setdefault("dispatch_active", False)
        safe.setdefault("roles_dispatched", "")

        if city_filter and safe["city"].lower() != city_filter.lower():
            continue
        if status_filter and safe["status"].lower() != status_filter.lower():
            continue

        companies.append(safe)

    return companies


# ---------------------------------------------------------------------------
# Phase 2 — Job request parsing and persistence
# ---------------------------------------------------------------------------

def parse_job_request(data: dict) -> dict:
    """
    Build a structured job object from raw form data.
    Notes are intentionally excluded — may contain raw operator remarks.
    """
    roles_raw = (data.get("roles_needed") or data.get("requested_roles_headcount") or "").strip()
    location  = (data.get("location") or "").strip()

    # "A2 x2, V1 x1, Stagehand x4" → ["a2", "v1", "stagehand"]
    clean = re.sub(r"x\s*\d+", "", roles_raw, flags=re.IGNORECASE)
    role_keywords = [p.strip().lower() for p in re.split(r"[,;|]", clean) if p.strip()]

    # "Convention Center, DC" → ["convention", "center", "dc"]
    location_tokens = [w.lower() for w in re.split(r"[\s,]+", location) if len(w) > 1]

    return {
        "request_id":      data.get("request_id") or f"req_{uuid4().hex}",
        "roles_needed":    roles_raw,
        "role_keywords":   role_keywords,
        "event_date":      (data.get("event_date") or "").strip(),
        "shift_window":    (data.get("shift_window") or "").strip(),
        "location":        location,
        "location_tokens": location_tokens,
        "created_at":      int(time.time()),
        # notes deliberately omitted
    }


def save_job_request(job: dict) -> None:
    """Append one job request to labor_job_requests.jsonl (append-only)."""
    JOB_REQUESTS_PATH.parent.mkdir(exist_ok=True)
    with JOB_REQUESTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(job, ensure_ascii=False) + "\n")


def load_job_request(request_id: str) -> dict | None:
    """Return a job request dict by request_id, or None if not found."""
    if not JOB_REQUESTS_PATH.exists():
        return None
    try:
        for line in JOB_REQUESTS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("request_id") == request_id:
                    return obj
            except Exception:
                continue
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Phase 2 — Job-specific worker scoring
# ---------------------------------------------------------------------------
#
#  Dimension            Max pts   Notes
#  ──────────────────── ───────   ─────────────────────────────────────────
#  Role overlap          40       keyword match worker.role vs job.role_keywords
#  Market / location     25       token overlap worker.market vs job.location
#  Availability          20       ready=20, limited=10, else=0
#  Certifications        10       any cert tag or skill flag present
#  Transport              3       transport field truthy
#  Verified source        2       career_dna source
#                       ───
#                       100

def match_workers_to_job(job: dict) -> list[dict]:
    """
    Score every worker in the pool against a specific job request.
    Returns list of candidate dicts sorted by match score descending.
    Candidates below MIN_JOB_MATCH_SCORE are excluded.
    No PII is included in returned dicts.
    """
    career_workers = _load_from_career_dna()
    intake_workers = _load_from_intake_subs()
    merged: dict[str, dict] = {**intake_workers, **career_workers}

    role_keywords    = job.get("role_keywords") or []
    location_tokens  = job.get("location_tokens") or []

    candidates = []

    for profile in merged.values():
        cert_tags   = profile.get("cert_tags") or parse_cert_tags(profile.get("cert_raw", ""))
        skill_flags = detect_skill_flags(cert_tags)
        readiness   = normalize_readiness(profile.get("availability"))
        transport   = (profile.get("transport") or "").strip().lower()
        worker_role = (profile.get("role") or "").strip().lower()
        worker_mkt  = (profile.get("market") or "").strip().lower()

        score   = 0
        reasons = []

        # --- Role overlap (max 40) ---
        if worker_role and role_keywords:
            best = 0
            best_kw = ""
            for kw in role_keywords:
                if kw == worker_role or kw in worker_role or worker_role in kw:
                    best, best_kw = 40, kw
                    break
                parts_overlap = any(p in worker_role for p in kw.split() if len(p) > 1) or \
                                any(p in kw for p in worker_role.split() if len(p) > 1)
                if parts_overlap and best < 20:
                    best, best_kw = 20, kw
            score += best
            if best == 40:
                reasons.append(f"Role match: {best_kw.upper()}")
            elif best == 20:
                reasons.append(f"Partial role: {best_kw.upper()}")
        elif worker_role:
            # job has no role filter — partial credit
            score += 20
            reasons.append("Role on file")

        # --- Market / location (max 25) ---
        if worker_mkt and location_tokens:
            overlap = sum(1 for t in location_tokens if t in worker_mkt)
            if overlap >= 2:
                score += 25
                reasons.append("Strong market match")
            elif overlap == 1:
                score += 15
                reasons.append("Partial market match")
        elif worker_mkt:
            score += 10
            reasons.append("Market on file")

        # --- Availability (max 20) ---
        if readiness == "ready":
            score += 20
            reasons.append("Available now")
        elif readiness == "limited":
            score += 10
            reasons.append("Limited availability")

        # --- Certifications (max 10) ---
        if cert_tags or skill_flags:
            score += 10
            if skill_flags:
                reasons.append(f"Skills: {', '.join(skill_flags[:3])}")

        # --- Transport (max 3) ---
        if transport and transport not in ("no", "none", "false", "0"):
            score += 3

        # --- Verified source (max 2) ---
        if profile.get("source") == "career_dna":
            score += 2

        score = min(score, 100)

        if score < MIN_JOB_MATCH_SCORE:
            continue

        candidates.append({
            "display_id":  _display_token(profile["worker_id"]),
            "role":        profile.get("role") or "",
            "market":      profile.get("market") or "",
            "readiness":   readiness,
            "score":       score,
            "skill_flags": skill_flags,
            "cert_count":  len(cert_tags),
            "reasons":     reasons,
            "rate_band":   "Market Rate",
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Phase 3 — Dispatch assignment persistence and workflow
#
# Assignment schema (one JSON object per line, append-only):
#   contact_req_id  — unique connection request ID
#   request_id      — job request this assignment belongs to
#   display_id      — opaque worker token (WRK-XXXXXX), never real worker_id
#   status          — "pending" | "approved" | "rejected"
#   worker_role     — role string from match results (no PII)
#   worker_market   — market string from match results (no PII)
#   match_score     — integer score at time of request
#   created_at      — Unix timestamp
#
# Status updates are appended as new lines; latest entry per
# contact_req_id wins (same append-only pattern as career_dna_ledger).
# ---------------------------------------------------------------------------

def save_dispatch_assignment(data: dict) -> None:
    """Append a new dispatch assignment entry (status=pending on creation)."""
    DISPATCH_ASSIGNMENTS_PATH.parent.mkdir(exist_ok=True)
    entry = {
        "contact_req_id": data["contact_req_id"],
        "request_id":     data.get("request_id", ""),
        "display_id":     data.get("display_id", ""),
        "status":         data.get("status", "pending"),
        "worker_role":    data.get("worker_role", ""),
        "worker_market":  data.get("worker_market", ""),
        "match_score":    int(data.get("match_score") or 0),
        "created_at":     int(time.time()),
        # no PII: no real worker_id, no email, no phone
    }
    with DISPATCH_ASSIGNMENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_latest_assignments() -> dict[str, dict]:
    """Read all assignment lines; deduplicate by contact_req_id keeping latest."""
    if not DISPATCH_ASSIGNMENTS_PATH.exists():
        return {}
    latest: dict[str, dict] = {}
    try:
        for line in DISPATCH_ASSIGNMENTS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                cid = obj.get("contact_req_id")
                if cid:
                    latest[cid] = obj   # later lines overwrite earlier ones
            except Exception:
                continue
    except Exception:
        return {}
    return latest


def update_dispatch_assignment(contact_req_id: str, status: str) -> None:
    """
    Append a status-update entry for an existing assignment.
    Carries forward all context fields from the original record.
    No-op if contact_req_id is not found.
    """
    existing = _load_latest_assignments().get(contact_req_id)
    if not existing:
        return
    entry = {**existing, "status": status, "created_at": int(time.time())}
    DISPATCH_ASSIGNMENTS_PATH.parent.mkdir(exist_ok=True)
    with DISPATCH_ASSIGNMENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_assignment_status(contact_req_id: str) -> dict | None:
    """Return the latest assignment dict for a contact_req_id, or None."""
    return _load_latest_assignments().get(contact_req_id)


def get_existing_assignments(request_id: str) -> dict[str, str]:
    """
    Return {display_id: status} for all assignments belonging to a job request.
    Used by the results page to suppress duplicate contact buttons.
    """
    result: dict[str, str] = {}
    for assignment in _load_latest_assignments().values():
        if assignment.get("request_id") == request_id:
            did = assignment.get("display_id", "")
            if did:
                result[did] = assignment.get("status", "pending")
    return result


def _load_all_job_requests() -> dict[str, dict]:
    """Load all job requests keyed by request_id (for queue join)."""
    if not JOB_REQUESTS_PATH.exists():
        return {}
    jobs: dict[str, dict] = {}
    try:
        for line in JOB_REQUESTS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                rid = obj.get("request_id")
                if rid:
                    jobs[rid] = obj
            except Exception:
                continue
    except Exception:
        return {}
    return jobs


def load_dispatch_queue(status_filter: str = "") -> list[dict]:
    """
    Return all dispatch assignments with job context, newest first.
    Optional status_filter: "pending" | "approved" | "rejected" | "" (all).
    No PII in returned dicts.
    """
    assignments = _load_latest_assignments()
    jobs        = _load_all_job_requests()

    queue = []
    for assignment in assignments.values():
        if status_filter and assignment.get("status") != status_filter:
            continue
        rid = assignment.get("request_id", "")
        job = jobs.get(rid, {})
        queue.append({
            "contact_req_id": assignment.get("contact_req_id", ""),
            "request_id":     rid,
            "display_id":     assignment.get("display_id", ""),
            "status":         assignment.get("status", "pending"),
            "worker_role":    assignment.get("worker_role", ""),
            "worker_market":  assignment.get("worker_market", ""),
            "match_score":    assignment.get("match_score", 0),
            "created_at":     assignment.get("created_at", 0),
            "job_roles":      job.get("roles_needed", ""),
            "job_location":   job.get("location", ""),
            "job_date":       job.get("event_date", ""),
            "job_shift":      job.get("shift_window", ""),
        })

    queue.sort(key=lambda a: a.get("created_at", 0), reverse=True)
    return queue
