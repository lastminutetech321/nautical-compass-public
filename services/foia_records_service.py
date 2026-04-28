from typing import Any, Dict, List


class FOIARecordsServiceError(Exception):
    pass


def _normalize_target_type(complaint: Dict[str, Any]) -> str:
    target_type = (complaint.get("targetType", "") or "").strip().lower()
    target_name = (complaint.get("targetName", "") or "").strip().lower()

    if target_type:
        return target_type

    government_terms = [
        "police",
        "sheriff",
        "department",
        "agency",
        "city",
        "county",
        "state",
        "officer",
        "judge",
        "court",
        "board",
        "commission",
        "school district",
        "municipality",
    ]

    if any(term in target_name for term in government_terms):
        return "government"

    return "private"


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_records_request_packet(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise FOIARecordsServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise FOIARecordsServiceError("No complaints found in intake_state.")

    complaint = None
    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise FOIARecordsServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    target_type = _normalize_target_type(complaint)
    target_name = complaint.get("targetName", "")
    target_department = complaint.get("targetDepartment", "")
    target_person = complaint.get("targetPerson", "")
    short_title = complaint.get("shortTitle", "")
    what_happened = complaint.get("whatHappened", "")
    timeline_events = complaint.get("timelineEvents", []) or []
    related_evidence_ids = complaint.get("relatedEvidenceIds", []) or []

    record_categories: List[str] = []
    reasons: List[str] = []

    if target_type == "government":
        record_categories.extend([
            "incident_reports",
            "body_camera_or_video",
            "dispatch_logs",
            "policies_and_procedures",
            "communications_records",
        ])
        reasons.append("Government target suggests public records route.")
    else:
        record_categories.extend([
            "contract_records",
            "invoice_records",
            "communications_records",
            "account_notes",
        ])
        reasons.append("Private target suggests document demand / records preservation route.")

    if target_department:
        record_categories.append("department_records")
    if target_person:
        record_categories.append("personnel_or_actor_specific_records")
    if timeline_events:
        record_categories.append("date_specific_event_records")
    if related_evidence_ids:
        record_categories.append("supporting_source_records")

    record_categories = _dedupe(record_categories)

    request_scope = {
        "targetType": target_type,
        "targetName": target_name,
        "targetDepartment": target_department,
        "targetPerson": target_person,
        "subject": short_title,
        "factSummary": what_happened,
        "timelineEventCount": len(timeline_events),
        "relatedEvidenceCount": len(related_evidence_ids),
        "recordCategories": record_categories,
    }

    recommended_next_actions: List[str] = []
    if target_type == "government":
        recommended_next_actions.extend([
            "draft_public_records_request",
            "identify_custodian_of_records",
            "narrow_date_range_if_needed",
        ])
    else:
        recommended_next_actions.extend([
            "draft_document_demand",
            "send_preservation_notice",
            "identify_record_holder",
        ])

    if timeline_events:
        recommended_next_actions.append("attach_timeline_to_request")
    if related_evidence_ids:
        recommended_next_actions.append("cross_reference_existing_evidence")

    return {
        "complaintId": complaint.get("complaintId", ""),
        "requestType": "public_records" if target_type == "government" else "document_demand",
        "requestScope": request_scope,
        "reasons": reasons,
        "recommendedNextActions": _dedupe(recommended_next_actions),
        "message": "Records request packet ready",
        "note": "This is an intake-level records request builder, not legal advice or a final filing recommendation.",
    }


if __name__ == "__main__":
    demo_state = {
        "complaintProfile": {
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "targetType": "government",
                    "targetName": "City Police Department",
                    "targetDepartment": "Internal Affairs",
                    "targetPerson": "Officer Smith",
                    "shortTitle": "Unlawful stop",
                    "whatHappened": "Officer stopped and detained me, then searched my property.",
                    "relatedEvidenceIds": ["ev-1"],
                    "timelineEvents": [
                        {
                            "eventId": "t1",
                            "date": "2026-03-28",
                            "event": "Stop occurred",
                        }
                    ],
                }
            ]
        }
    }

    result = build_records_request_packet(demo_state, "complaint-1")
    print("complaintId:", result["complaintId"])
    print("requestType:", result["requestType"])
    print("recordCategories:", result["requestScope"]["recordCategories"])
    print("recommendedNextActions:", result["recommendedNextActions"])
