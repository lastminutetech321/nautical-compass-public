"""
Phase 1 Labor Matching — reads worker profiles from JSONL ledgers,
scores and ranks them for the /labor/matches dispatch pool view.

Data sources (read-only):
  runtime/career_dna_ledger.jsonl    — primary: labor_profile_submitted events
  runtime/intake_submissions.jsonl   — secondary: intake_type=="labor" records

Privacy rules enforced here:
  - No email, phone, exact address, or raw notes exposed in returned dicts
  - Worker identity shown only as a shortened display token
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CAREER_DNA_PATH = Path("runtime/career_dna_ledger.jsonl")
INTAKE_SUBS_PATH = Path("runtime/intake_submissions.jsonl")

MIN_READINESS_SCORE = 30  # profiles below this are hidden from the pool


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
