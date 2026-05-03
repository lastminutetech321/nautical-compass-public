import re
from typing import Any, Dict, List, Optional


class TimelineServiceError(Exception):
    pass


# ---------------------------------------------------------------------------
# Complaint-draft timeline analysis
# ---------------------------------------------------------------------------

_TEMPORAL_PREFIXES = re.compile(
    r"\b(on|in|around|approximately|before|after|by|during|when|following|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)

_DATE_PATTERN = re.compile(
    r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)


def _infer_events_from_text(text: str) -> List[Dict[str, str]]:
    """Extract probable timeline events from a narrative block."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    events: List[Dict[str, str]] = []
    for i, sent in enumerate(sentences):
        sent = sent.strip()
        if not sent:
            continue
        date_match = _DATE_PATTERN.search(sent)
        has_temporal = bool(_TEMPORAL_PREFIXES.search(sent))
        if date_match or has_temporal or len(sent) > 40:
            date_val = date_match.group(0) if date_match else "[FACT NEEDED: event date]"
            events.append({
                "eventId": f"inferred-{i + 1}",
                "date": date_val,
                "event": sent[:120] + ("..." if len(sent) > 120 else ""),
                "description": sent,
                "actor": "",
                "source": "inferred_from_narrative",
                "inferred": True,
            })
    return events[:10]


def build_complaint_timeline(
    intake_state: Dict[str, Any],
    complaint_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a structured timeline for complaint drafting.
    Uses timelineEvents array when present; infers events from whatHappened when absent.
    """
    if not isinstance(intake_state, dict):
        raise TimelineServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise TimelineServiceError("No complaints found in intake_state.")

    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise TimelineServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    structured_events = complaint.get("timelineEvents", []) or []
    source = "structured"
    inferred = False

    if not structured_events:
        narrative = complaint.get("whatHappened", "") or complaint.get("plainLanguageSummary", "") or ""
        structured_events = _infer_events_from_text(narrative)
        source = "inferred"
        inferred = True

    sorted_events = sorted(structured_events, key=lambda x: x.get("date", ""))
    strength = assess_chronology_strength({"events": sorted_events, "inferred": inferred})

    return {
        "complaintId": complaint.get("complaintId", ""),
        "eventCount": len(sorted_events),
        "events": sorted_events,
        "source": source,
        "inferred": inferred,
        "strength": strength,
        "note": (
            "Timeline inferred from narrative — dates marked [FACT NEEDED] must be verified and corrected before filing."
            if inferred
            else "Timeline built from structured intake events."
        ),
    }


def assess_chronology_strength(timeline_result: Dict[str, Any]) -> str:
    """Return 'strong', 'moderate', or 'weak' based on timeline completeness."""
    events = timeline_result.get("events", [])
    inferred = timeline_result.get("inferred", False)

    if not events:
        return "weak"

    has_real_dates = any(
        not str(e.get("date", "")).startswith("[FACT NEEDED")
        for e in events
    )

    if len(events) >= 3 and has_real_dates and not inferred:
        return "strong"
    if len(events) >= 2 and has_real_dates:
        return "moderate"
    if events:
        return "weak"
    return "weak"


def get_timeline_summary(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise TimelineServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []

    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise TimelineServiceError(f"Complaint not found: {complaint_id}")

        events = complaint.get("timelineEvents", []) or []
        return {
            "complaintId": complaint_id,
            "eventCount": len(events),
            "events": sorted(events, key=lambda x: x.get("date", "")),
        }

    all_events: List[Dict[str, Any]] = []
    for complaint in complaints:
        cid = complaint.get("complaintId", "")
        for event in complaint.get("timelineEvents", []) or []:
            all_events.append(
                {
                    **event,
                    "complaintId": cid,
                }
            )

    return {
        "complaintId": None,
        "eventCount": len(all_events),
        "events": sorted(all_events, key=lambda x: x.get("date", "")),
    }


def add_timeline_event(
    intake_state: Dict[str, Any],
    complaint_id: str,
    event_data: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise TimelineServiceError("intake_state must be a dictionary.")
    if not complaint_id:
        raise TimelineServiceError("complaint_id is required.")
    if not isinstance(event_data, dict):
        raise TimelineServiceError("event_data must be a dictionary.")

    state = dict(intake_state)
    complaints = state.setdefault("complaintProfile", {}).setdefault("complaints", [])

    complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
    if complaint is None:
        raise TimelineServiceError(f"Complaint not found: {complaint_id}")

    complaint.setdefault("timelineEvents", [])

    event = {
        "eventId": event_data.get("eventId", f"timeline-{len(complaint['timelineEvents']) + 1}"),
        "date": event_data.get("date", ""),
        "event": event_data.get("event", ""),
        "description": event_data.get("description", ""),
        "actor": event_data.get("actor", ""),
        "source": event_data.get("source", ""),
    }

    complaint["timelineEvents"].append(event)
    return state


def build_timeline_packet(intake_state: Dict[str, Any], complaint_id: str) -> Dict[str, Any]:
    summary = get_timeline_summary(intake_state, complaint_id)

    return {
        "complaintId": complaint_id,
        "eventCount": summary["eventCount"],
        "timeline": summary["events"],
        "message": "Timeline packet ready for review",
    }


if __name__ == "__main__":
    demo_state = {
        "complaintProfile": {
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "timelineEvents": [],
                }
            ]
        }
    }

    demo_state = add_timeline_event(
        demo_state,
        "complaint-1",
        {
            "eventId": "t1",
            "date": "2026-03-28",
            "event": "Invoice sent",
            "description": "Invoice emailed to company.",
            "actor": "user",
            "source": "email",
        },
    )

    demo_state = add_timeline_event(
        demo_state,
        "complaint-1",
        {
            "eventId": "t2",
            "date": "2026-03-29",
            "event": "Payment follow-up",
            "description": "Follow-up text sent regarding payment.",
            "actor": "user",
            "source": "sms",
        },
    )

    packet = build_timeline_packet(demo_state, "complaint-1")
    print("complaintId:", packet["complaintId"])
    print("eventCount:", packet["eventCount"])
    print("firstEvent:", packet["timeline"][0]["event"])
    print("message:", packet["message"])
