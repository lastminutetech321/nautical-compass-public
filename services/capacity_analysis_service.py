from typing import Any, Dict, List


class CapacityAnalysisServiceError(Exception):
    pass


def _safe_bool(value: Any) -> bool:
    return bool(value)


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

    return "company"


def _derive_capacity_path(complaint: Dict[str, Any]) -> Dict[str, Any]:
    target_type = _normalize_target_type(complaint)
    target_person = complaint.get("targetPerson", "")
    target_department = complaint.get("targetDepartment", "")
    desired_outcome = (complaint.get("desiredOutcome", "") or "").lower()
    property_damage = _safe_bool(complaint.get("propertyDamageClaimed"))
    injury_claimed = _safe_bool(complaint.get("injuryClaimed"))
    financial_loss = complaint.get("financialLossAmount", 0) or 0

    reasons: List[str] = []
    capacity_options: List[str] = []
    relief_track = "unclear"

    if target_type == "government":
        reasons.append("Target appears governmental or public-facing.")
        capacity_options.append("official_capacity_review")

        if target_person:
            reasons.append("Specific public actor identified.")
            capacity_options.append("individual_capacity_review")

        if target_department:
            reasons.append("Agency or department identified.")

        if "injunction" in desired_outcome or "stop" in desired_outcome or "policy" in desired_outcome:
            reasons.append("Requested relief suggests prospective official-capacity review.")
            relief_track = "prospective_relief"

        elif injury_claimed or property_damage or float(financial_loss) > 0:
            reasons.append("Damages-style allegations suggest individual-capacity review may matter.")
            relief_track = "damages"

        else:
            relief_track = "mixed"

    else:
        reasons.append("Target appears private rather than governmental.")
        capacity_options.append("private_actor_path")

        if target_person:
            reasons.append("Specific private actor identified.")
            capacity_options.append("individual_actor_review")

        if "payment" in desired_outcome or "refund" in desired_outcome or float(financial_loss) > 0:
            relief_track = "damages"
        else:
            relief_track = "contract_or_dispute_relief"

    return {
        "targetType": target_type,
        "capacityOptions": capacity_options,
        "reliefTrack": relief_track,
        "reasons": reasons,
    }


def analyze_capacity(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise CapacityAnalysisServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise CapacityAnalysisServiceError("No complaints found in intake_state.")

    complaint = None
    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise CapacityAnalysisServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    path = _derive_capacity_path(complaint)
    target_type = path["targetType"]
    relief_track = path["reliefTrack"]

    recommended_next_actions: List[str] = []

    if target_type == "government":
        if "official_capacity_review" in path["capacityOptions"]:
            recommended_next_actions.append("review_official_capacity_path")
        if "individual_capacity_review" in path["capacityOptions"]:
            recommended_next_actions.append("review_individual_capacity_path")
        if relief_track == "prospective_relief":
            recommended_next_actions.append("review_ex_parte_young_style_relief")
        if relief_track == "damages":
            recommended_next_actions.append("review_immunity_and_damages_path")
    else:
        recommended_next_actions.append("review_private_actor_claim_path")
        if "individual_actor_review" in path["capacityOptions"]:
            recommended_next_actions.append("identify_personal_actor_conduct")

    return {
        "complaintId": complaint.get("complaintId", ""),
        "targetName": complaint.get("targetName", ""),
        "targetPerson": complaint.get("targetPerson", ""),
        "targetDepartment": complaint.get("targetDepartment", ""),
        "capacityAnalysis": path,
        "recommendedNextActions": recommended_next_actions,
        "note": "This is an intake-level capacity screen for routing and issue-spotting, not legal advice.",
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
                    "desiredOutcome": "Injunction to stop enforcement and damages for loss",
                    "financialLossAmount": 2500,
                    "injuryClaimed": True,
                    "propertyDamageClaimed": False,
                }
            ]
        }
    }

    result = analyze_capacity(demo_state, "complaint-1")
    print("complaintId:", result["complaintId"])
    print("targetType:", result["capacityAnalysis"]["targetType"])
    print("capacityOptions:", result["capacityAnalysis"]["capacityOptions"])
    print("reliefTrack:", result["capacityAnalysis"]["reliefTrack"])
    print("recommendedNextActions:", result["recommendedNextActions"])
