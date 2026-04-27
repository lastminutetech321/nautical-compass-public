from typing import Any, Dict, List


class EvidenceServiceError(Exception):
    pass


def _safe_bool(value: Any) -> bool:
    return bool(value)


def get_evidence_summary(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise EvidenceServiceError("intake_state must be a dictionary.")

    evidence_profile = intake_state.get("evidenceProfile", {}) or {}
    evidence_items = evidence_profile.get("evidenceItems", []) or []

    return {
        "hasEvidence": _safe_bool(evidence_profile.get("hasEvidence")) or len(evidence_items) > 0,
        "evidenceCount": len(evidence_items),
        "items": evidence_items,
    }


def add_evidence_item(
    intake_state: Dict[str, Any],
    evidence_item: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise EvidenceServiceError("intake_state must be a dictionary.")
    if not isinstance(evidence_item, dict):
        raise EvidenceServiceError("evidence_item must be a dictionary.")

    state = dict(intake_state)
    state.setdefault("evidenceProfile", {})
    state["evidenceProfile"].setdefault("evidenceItems", [])

    item = {
        "evidenceId": evidence_item.get("evidenceId", f"ev-{len(state['evidenceProfile']['evidenceItems']) + 1}"),
        "label": evidence_item.get("label", ""),
        "type": evidence_item.get("type", "unknown"),
        "description": evidence_item.get("description", ""),
        "source": evidence_item.get("source", ""),
        "fileName": evidence_item.get("fileName", ""),
        "filePath": evidence_item.get("filePath", ""),
        "date": evidence_item.get("date", ""),
        "linkedComplaintIds": evidence_item.get("linkedComplaintIds", []),
        "tags": evidence_item.get("tags", []),
    }

    state["evidenceProfile"]["evidenceItems"].append(item)
    state["evidenceProfile"]["hasEvidence"] = True
    return state


def link_evidence_to_complaint(
    intake_state: Dict[str, Any],
    complaint_id: str,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise EvidenceServiceError("intake_state must be a dictionary.")
    if not complaint_id:
        raise EvidenceServiceError("complaint_id is required.")
    if not evidence_id:
        raise EvidenceServiceError("evidence_id is required.")

    state = dict(intake_state)

    complaint_profile = state.setdefault("complaintProfile", {})
    complaints = complaint_profile.setdefault("complaints", [])

    evidence_profile = state.setdefault("evidenceProfile", {})
    evidence_items = evidence_profile.setdefault("evidenceItems", [])

    complaint_found = False
    for complaint in complaints:
        if complaint.get("complaintId") == complaint_id:
            complaint.setdefault("relatedEvidenceIds", [])
            if evidence_id not in complaint["relatedEvidenceIds"]:
                complaint["relatedEvidenceIds"].append(evidence_id)
            complaint_found = True
            break

    if not complaint_found:
        raise EvidenceServiceError(f"Complaint not found: {complaint_id}")

    evidence_found = False
    for evidence in evidence_items:
        if evidence.get("evidenceId") == evidence_id:
            evidence.setdefault("linkedComplaintIds", [])
            if complaint_id not in evidence["linkedComplaintIds"]:
                evidence["linkedComplaintIds"].append(complaint_id)
            evidence_found = True
            break

    if not evidence_found:
        raise EvidenceServiceError(f"Evidence not found: {evidence_id}")

    return state


if __name__ == "__main__":
    demo_state = {
        "complaintProfile": {
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "relatedEvidenceIds": [],
                }
            ]
        },
        "evidenceProfile": {
            "hasEvidence": False,
            "evidenceItems": [],
        },
    }

    demo_state = add_evidence_item(
        demo_state,
        {
            "evidenceId": "ev-1",
            "label": "Invoice PDF",
            "type": "document",
            "description": "Invoice showing unpaid balance",
            "source": "user_upload",
            "fileName": "invoice.pdf",
            "filePath": "/uploads/invoice.pdf",
            "date": "2026-03-29",
            "tags": ["invoice", "payment"],
        },
    )

    demo_state = link_evidence_to_complaint(demo_state, "complaint-1", "ev-1")
    summary = get_evidence_summary(demo_state)

    print("hasEvidence:", summary["hasEvidence"])
    print("evidenceCount:", summary["evidenceCount"])
    print("firstEvidenceId:", summary["items"][0]["evidenceId"])
    print("linkedComplaintIds:", summary["items"][0]["linkedComplaintIds"])
