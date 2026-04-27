from typing import Any, Dict, List


class AffidavitDeclarationServiceError(Exception):
    pass


def _safe_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_affidavit_declaration_packet(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise AffidavitDeclarationServiceError("intake_state must be a dictionary.")

    identity = intake_state.get("identityProfile", {}) or {}
    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []

    complaint = None
    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise AffidavitDeclarationServiceError(f"Complaint not found: {complaint_id}")
    elif complaints:
        complaint = complaints[0]
    else:
        complaint = {}

    full_name = identity.get("fullLegalName", "")
    email = identity.get("email", "")
    phone = identity.get("phone", "")

    short_title = complaint.get("shortTitle", "")
    summary = complaint.get("plainLanguageSummary", "")
    facts = complaint.get("whatHappened", "")
    desired_outcome = complaint.get("desiredOutcome", "")
    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    work_loss = _safe_number(complaint.get("workLossAmount"))
    related_evidence_ids = complaint.get("relatedEvidenceIds", []) or []
    timeline_events = complaint.get("timelineEvents", []) or []

    declaration_points: List[str] = []

    if summary:
        declaration_points.append(summary)
    if facts:
        declaration_points.append(facts)
    if financial_loss > 0:
        declaration_points.append(f"Affiant alleges financial loss in the amount of {financial_loss:.2f}.")
    if work_loss > 0:
        declaration_points.append(f"Affiant alleges work-related loss in the amount of {work_loss:.2f}.")
    if desired_outcome:
        declaration_points.append(f"Affiant seeks the following outcome: {desired_outcome}.")

    if not declaration_points:
        declaration_points.append("Affiant states that further fact development is required.")

    packet = {
        "affiantName": full_name,
        "affiantEmail": email,
        "affiantPhone": phone,
        "title": short_title or "Affidavit / Declaration Draft",
        "complaintId": complaint.get("complaintId", ""),
        "targetName": complaint.get("targetName", ""),
        "declarationPoints": declaration_points,
        "timelineEventCount": len(timeline_events),
        "relatedEvidenceIds": related_evidence_ids,
        "verificationClause": "I declare under penalty of perjury that the foregoing is true and correct to the best of my knowledge.",
    }

    recommended_next_actions = [
        "review_affidavit_facts",
        "attach_evidence_index" if related_evidence_ids else "gather_supporting_evidence",
        "attach_timeline_summary" if timeline_events else "build_timeline",
        "finalize_signature_block",
    ]

    return {
        "documentType": "affidavit_declaration",
        "status": "generated",
        "packet": packet,
        "recommendedNextActions": _dedupe(recommended_next_actions),
        "message": "Affidavit / declaration packet ready",
        "note": "This is an intake-level affidavit/declaration builder for preparation support, not legal advice.",
    }


if __name__ == "__main__":
    demo_state = {
        "identityProfile": {
            "fullLegalName": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-123-4567",
        },
        "complaintProfile": {
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "targetName": "Demo Company",
                    "shortTitle": "Unpaid work",
                    "plainLanguageSummary": "Completed work was not paid.",
                    "whatHappened": "Work was completed, invoice sent, and payment was not issued.",
                    "desiredOutcome": "Full payment of outstanding invoice",
                    "financialLossAmount": 1200,
                    "workLossAmount": 0,
                    "relatedEvidenceIds": ["ev-1"],
                    "timelineEvents": [
                        {"eventId": "t1", "date": "2026-03-28", "event": "Invoice sent"}
                    ],
                }
            ]
        },
    }

    result = build_affidavit_declaration_packet(demo_state, "complaint-1")
    print("documentType:", result["documentType"])
    print("status:", result["status"])
    print("title:", result["packet"]["title"])
    print("recommendedNextActions:", result["recommendedNextActions"])
