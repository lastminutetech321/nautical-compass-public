from typing import Any, Dict, List

from runtime.document_history_logger import append_document_record
from utils.spec_loader import load_spec


class ComplaintServiceError(Exception):
    pass


def _safe_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_bool(value: Any) -> bool:
    return bool(value)


def get_complaint_summary(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ComplaintServiceError("intake_state must be a dictionary.")

    complaint_profile = intake_state.get("complaintProfile", {}) or {}
    complaints = complaint_profile.get("complaints", []) or []

    if not complaints:
        return {
            "hasComplaint": False,
            "complaintCount": 0,
            "items": [],
        }

    items = []
    for complaint in complaints:
        items.append(
            {
                "complaintId": complaint.get("complaintId", ""),
                "status": complaint.get("status", "draft"),
                "category": complaint.get("category", ""),
                "subcategory": complaint.get("subcategory", ""),
                "targetName": complaint.get("targetName", ""),
                "shortTitle": complaint.get("shortTitle", ""),
                "plainLanguageSummary": complaint.get("plainLanguageSummary", ""),
                "financialLossAmount": _safe_number(complaint.get("financialLossAmount")),
                "injuryClaimed": _safe_bool(complaint.get("injuryClaimed")),
                "propertyDamageClaimed": _safe_bool(complaint.get("propertyDamageClaimed")),
                "creditImpactClaimed": _safe_bool(complaint.get("creditImpactClaimed")),
                "relatedEvidenceIds": complaint.get("relatedEvidenceIds", []) or [],
                "timelineEvents": complaint.get("timelineEvents", []) or [],
            }
        )

    return {
        "hasComplaint": True,
        "complaintCount": len(items),
        "items": items,
    }


def add_complaint(
    intake_state: Dict[str, Any],
    complaint_data: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ComplaintServiceError("intake_state must be a dictionary.")
    if not isinstance(complaint_data, dict):
        raise ComplaintServiceError("complaint_data must be a dictionary.")

    state = dict(intake_state)
    state.setdefault("complaintProfile", {})
    state["complaintProfile"].setdefault("complaints", [])

    complaint_template = load_spec("complaint_curation_schema").get("complaintTemplate", {})

    new_complaint = {
        **complaint_template,
        **complaint_data,
    }

    if not new_complaint.get("complaintId"):
        new_complaint["complaintId"] = f"complaint-{len(state['complaintProfile']['complaints']) + 1}"

    state["complaintProfile"]["complaints"].append(new_complaint)
    state["complaintProfile"]["hasComplaintOrDispute"] = True
    return state


def build_complaint_packet(
    user_id: str,
    intake_state: Dict[str, Any],
    complaint_id: str,
) -> Dict[str, Any]:
    if not user_id:
        raise ComplaintServiceError("user_id is required.")
    if not isinstance(intake_state, dict):
        raise ComplaintServiceError("intake_state must be a dictionary.")
    if not complaint_id:
        raise ComplaintServiceError("complaint_id is required.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)

    if complaint is None:
        raise ComplaintServiceError(f"Complaint not found: {complaint_id}")

    packet = {
        "complaintId": complaint.get("complaintId", ""),
        "status": complaint.get("status", "draft"),
        "category": complaint.get("category", ""),
        "subcategory": complaint.get("subcategory", ""),
        "targetName": complaint.get("targetName", ""),
        "targetDepartment": complaint.get("targetDepartment", ""),
        "targetPerson": complaint.get("targetPerson", ""),
        "shortTitle": complaint.get("shortTitle", ""),
        "plainLanguageSummary": complaint.get("plainLanguageSummary", ""),
        "whatHappened": complaint.get("whatHappened", ""),
        "whatWasSaid": complaint.get("whatWasSaid", ""),
        "financialLossAmount": _safe_number(complaint.get("financialLossAmount")),
        "workLossAmount": _safe_number(complaint.get("workLossAmount")),
        "timeLostHours": _safe_number(complaint.get("timeLostHours")),
        "harmTypes": complaint.get("harmTypes", []) or [],
        "relatedEvidenceIds": complaint.get("relatedEvidenceIds", []) or [],
        "timelineEvents": complaint.get("timelineEvents", []) or [],
        "desiredOutcome": complaint.get("desiredOutcome", ""),
        "curation": complaint.get("curation", {}) or {},
    }

    updated_state = append_document_record(
        user_id,
        intake_state,
        {
            "documentId": f"doc-{complaint_id}",
            "documentType": "complaint_summary",
            "title": "Complaint Packet Draft",
            "fileName": f"{complaint_id}-packet.json",
            "filePath": f"/generated/{complaint_id}-packet.json",
            "status": "generated",
            "linkedComplaintId": complaint_id,
            "linkedEvidenceIds": packet["relatedEvidenceIds"],
            "notes": "complaint packet generated",
        },
    )

    return {
        "documentType": "complaint_summary",
        "status": "generated",
        "valid": True,
        "message": "Complaint packet ready for review",
        "packet": packet,
        "intakeState": updated_state,
    }


if __name__ == "__main__":
    demo_state = {
        "complaintProfile": {
            "hasComplaintOrDispute": False,
            "complaints": [],
        }
    }

    demo_state = add_complaint(
        demo_state,
        {
            "complaintId": "complaint-1",
            "status": "draft",
            "category": "payment_issue",
            "targetName": "Demo Company",
            "shortTitle": "Unpaid work",
            "plainLanguageSummary": "The company failed to pay for completed work.",
            "whatHappened": "Work was completed and payment was not issued.",
            "financialLossAmount": 1200,
            "relatedEvidenceIds": ["ev-1", "ev-2"],
            "timelineEvents": [{"date": "2026-03-29", "event": "Invoice sent"}],
            "desiredOutcome": "Full payment",
        },
    )

    summary = get_complaint_summary(demo_state)
    packet_result = build_complaint_packet("demo-user", demo_state, "complaint-1")

    print("complaintCount:", summary["complaintCount"])
    print("hasComplaint:", summary["hasComplaint"])
    print("documentType:", packet_result["documentType"])
    print("message:", packet_result["message"])
