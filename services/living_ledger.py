"""
Living Ledger — Phase 1 unified event writer.

Appends enriched events to runtime/event_ledger.jsonl (all rails).
Mirrors labor-profile events to runtime/career_dna_ledger.jsonl when
rail == "labor" and a worker_id is present.

Never alters existing EventLedger or CareerDNALedger class behavior.
Never stores raw IP addresses.
Never exposes worker phone/email to company-rail events.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import Request

RUNTIME = Path("runtime")
EVENT_LOG = RUNTIME / "event_ledger.jsonl"
DNA_LOG   = RUNTIME / "career_dna_ledger.jsonl"

LABOR_RAILS = {"labor"}


# ---------------------------------------------------------------------------
# Privacy-safe actor fingerprint
# ---------------------------------------------------------------------------

def get_actor_id(request: Request) -> str:
    """Return a hashed actor fingerprint derived from IP + User-Agent.
    Raw IP is never stored anywhere."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else ""
    if not ip and request.client:
        ip = request.client.host or ""
    ua = request.headers.get("user-agent", "")
    raw = f"{ip}|{ua}"
    return "anon_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Core writer
# ---------------------------------------------------------------------------

def write_event(
    *,
    rail: str,
    event_type: str,
    title: str,
    route: str = "",
    status: str = "ok",
    actor_id: Optional[str] = None,
    actor_type: str = "visitor",
    session_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    company_id: Optional[str] = None,
    intake_type: Optional[str] = None,
    next_action: str = "",
    residual_trigger: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append one living-ledger event to event_ledger.jsonl.

    For labor-rail events with a worker_id, also mirrors a summary
    record to career_dna_ledger.jsonl using the existing CareerDNA schema.
    """
    RUNTIME.mkdir(exist_ok=True)

    event: Dict[str, Any] = {
        "event_id":         f"evt_{uuid4().hex[:10]}",
        "ts":               int(time.time()),
        "rail":             rail,
        "event_type":       event_type,
        "actor_id":         actor_id,
        "actor_type":       actor_type,
        "session_id":       session_id or actor_id,
        "route":            route,
        "title":            title,
        "status":           status,
        "next_action":      next_action,
        "residual_trigger": residual_trigger,
        "worker_id":        worker_id,
        "company_id":       company_id,
        "intake_type":      intake_type,
        "payload":          payload or {},
    }

    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # Mirror to career_dna_ledger only for labor-rail events with a worker_id.
    # This preserves the existing CareerDNA schema exactly so existing readers work.
    if rail in LABOR_RAILS and worker_id:
        meta = payload or {}
        dna: Dict[str, Any] = {
            "ts":                  event["ts"],
            "worker_id":           worker_id,
            "event_type":          event_type,
            "role":                meta.get("role"),
            "company":             meta.get("company"),
            "venue":               meta.get("venue"),
            "market":              meta.get("market"),
            "shift_status":        None,
            "pay_band":            meta.get("pay_band"),
            "verification_source": "living_ledger",
            "certifications":      meta.get("certifications", []),
            "tools_used":          meta.get("tools_used", []),
            "payload": {
                "event_id":   event["event_id"],
                "title":      title,
                "route":      route,
                "intake_type": intake_type,
            },
        }
        with DNA_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dna, ensure_ascii=False) + "\n")

    return event


# ---------------------------------------------------------------------------
# Convenience wrappers — keep route files tidy
# ---------------------------------------------------------------------------

def log_page_view(
    request: Request,
    *,
    rail: str,
    event_type: str,
    title: str,
    next_action: str = "",
    residual_trigger: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """One-liner for simple page-view events."""
    actor = get_actor_id(request)
    write_event(
        rail=rail,
        event_type=event_type,
        title=title,
        route=str(request.url.path),
        actor_id=actor,
        actor_type="visitor",
        next_action=next_action,
        residual_trigger=residual_trigger,
        payload=extra or {},
    )


def log_intake_event(
    request: Request,
    *,
    intake_type: str,
    intake_id: Optional[str] = None,
    intake_score: Optional[int] = None,
    full_name: str = "",
) -> None:
    """Write intake submission events split by rail."""
    actor = get_actor_id(request)

    rail_map = {
        "legal":          "legal",
        "labor":          "labor",
        "worker_profile": "labor",
        "production":     "labor",
        "partner":        "system",
        "payment":        "system",
        "general":        "system",
    }
    rail = rail_map.get(intake_type, "system")

    next_action_map = {
        "legal":          "standing_analysis_review",
        "labor":          "labor_profile_review",
        "worker_profile": "career_dna_profile_build",
        "production":     "crew_dispatch_review",
        "partner":        "operator_onboarding_review",
        "payment":        "billing_dispute_review",
        "general":        "general_follow_up",
    }

    residual_map = {
        "legal":  "abandoned_intake_legal_or_labor",
        "labor":  "abandoned_intake_legal_or_labor",
        "worker_profile": "profile_not_completed",
    }

    write_event(
        rail=rail,
        event_type="intake_submitted",
        title=f"Intake submitted — {intake_type}",
        route="/intake",
        actor_id=actor,
        actor_type="visitor",
        intake_type=intake_type,
        next_action=next_action_map.get(intake_type, "general_follow_up"),
        residual_trigger=None,
        payload={
            "intake_id":    intake_id,
            "intake_score": intake_score,
            "intake_type":  intake_type,
            "name_hint":    full_name[:2] + "***" if full_name else "",
        },
    )
