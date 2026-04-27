from typing import Any, Dict, List


class JurisdictionServiceError(Exception):
    pass


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _safe_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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


def _derive_jurisdiction_track(intake_state: Dict[str, Any], complaint: Dict[str, Any]) -> Dict[str, Any]:
    target_type = _normalize_target_type(complaint)
    category = (complaint.get("category", "") or "").lower()
    desired_outcome = (complaint.get("desiredOutcome", "") or "").lower()

    injury_claimed = _safe_bool(complaint.get("injuryClaimed"))
    property_damage = _safe_bool(complaint.get("propertyDamageClaimed"))
    credit_impact = _safe_bool(complaint.get("creditImpactClaimed"))
    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    work_loss = _safe_number(complaint.get("workLossAmount"))
    has_evidence = _safe_bool(intake_state.get("evidenceProfile", {}).get("hasEvidence"))
    has_complaint = _safe_bool(intake_state.get("complaintProfile", {}).get("hasComplaintOrDispute"))

    recommendations: List[str] = []
    reasons: List[str] = []
    venue_notes: List[str] = []

    if target_type == "government":
        reasons.append("Target appears governmental or public-facing.")
        recommendations.append("federal_or_state_public_law_review")

        if "injunction" in desired_outcome or "stop" in desired_outcome or "policy" in desired_outcome:
            reasons.append("Requested relief suggests prospective public-law review.")
            recommendations.append("official_capacity_injunctive_review")

        if injury_claimed or property_damage or financial_loss > 0:
            reasons.append("Damages-style allegations may support civil rights or state-law review.")
            recommendations.append("damages_path_review")

    else:
        reasons.append("Target appears private rather than governmental.")
        recommendations.append("private_dispute_review")

        if category in {"payment_issue", "contract_issue", "invoice_issue"}:
            reasons.append("Complaint category suggests contract or collection path.")
            recommendations.append("state_contract_or_small_claims_review")

        if credit_impact:
            reasons.append("Credit-related harm may trigger consumer or reporting review.")
            recommendations.append("consumer_credit_review")

    if financial_loss > 0 or work_loss > 0:
        venue_notes.append("Monetary loss alleged; damages forum may be relevant.")

    if has_complaint and not has_evidence:
        venue_notes.append("Evidence needs strengthening before escalation.")
    elif has_evidence:
        venue_notes.append("Evidence present to support escalation review.")

    if category in {"consumer_issue", "credit_issue", "debt_issue"}:
        recommendations.append("regulatory_complaint_review")
        reasons.append("Complaint type may support regulator-facing path.")

    if "payment" in desired_outcome or "refund" in desired_outcome or "full payment" in desired_outcome:
        recommendations.append("demand_and_collection_review")
        reasons.append("Requested relief suggests demand or receivables path.")

    deduped_recommendations: List[str] = []
    for item in recommendations:
        if item not in deduped_recommendations:
            deduped_recommendations.append(item)

    if target_type == "government" and (
        injury_claimed or property_damage or financial_loss > 0
    ):
        primary_track = "public_law"
    elif category in {"payment_issue", "contract_issue", "invoice_issue"}:
        primary_track = "private_dispute"
    elif category in {"consumer_issue", "credit_issue", "debt_issue"}:
        primary_track = "regulatory_or_consumer"
    else:
        primary_track = "general_review"

    return {
        "targetType": target_type,
        "primaryTrack": primary_track,
        "recommendations": deduped_recommendations,
        "reasons": reasons,
        "venueNotes": venue_notes,
    }


def analyze_jurisdiction(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise JurisdictionServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise JurisdictionServiceError("No complaints found in intake_state.")

    complaint = None
    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise JurisdictionServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    analysis = _derive_jurisdiction_track(intake_state, complaint)

    next_actions: List[str] = []
    primary_track = analysis["primaryTrack"]

    if primary_track == "public_law":
        next_actions.extend([
            "review_standing",
            "review_capacity",
            "review_public_law_forum",
        ])
    elif primary_track == "private_dispute":
        next_actions.extend([
            "review_contract_and_collection_path",
            "review_demand_packet",
        ])
    elif primary_track == "regulatory_or_consumer":
        next_actions.extend([
            "review_regulatory_route",
            "review_consumer_statute_path",
        ])
    else:
        next_actions.extend([
            "review_fact_pattern",
            "clarify_forum_selection",
        ])

    return {
        "complaintId": complaint.get("complaintId", ""),
        "targetName": complaint.get("targetName", ""),
        "category": complaint.get("category", ""),
        "jurisdictionAnalysis": analysis,
        "recommendedNextActions": next_actions,
        "note": "This is an intake-level jurisdiction and routing screen, not legal advice or a final jurisdiction determination.",
    }


if __name__ == "__main__":
    demo_state = {
        "complaintProfile": {
            "hasComplaintOrDispute": True,
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "targetType": "government",
                    "targetName": "City Police Department",
                    "category": "civil_rights",
                    "desiredOutcome": "Injunction to stop enforcement and damages",
                    "financialLossAmount": 2500,
                    "injuryClaimed": True,
                    "propertyDamageClaimed": False,
                    "creditImpactClaimed": False,
                }
            ],
        },
        "evidenceProfile": {
            "hasEvidence": True,
        },
    }

    result = analyze_jurisdiction(demo_state, "complaint-1")
    print("complaintId:", result["complaintId"])
    print("primaryTrack:", result["jurisdictionAnalysis"]["primaryTrack"])
    print("recommendations:", result["jurisdictionAnalysis"]["recommendations"])
    print("venueNotes:", result["jurisdictionAnalysis"]["venueNotes"])
    print("recommendedNextActions:", result["recommendedNextActions"])
