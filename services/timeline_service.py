from typing import Any, Dict, List


class TimelineServiceError(Exception):
    pass


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
