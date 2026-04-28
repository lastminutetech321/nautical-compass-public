from typing import Any, Dict, List


class StandingAnalysisServiceError(Exception):
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


def _derive_injury_in_fact(complaint: Dict[str, Any]) -> Dict[str, Any]:
    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    work_loss = _safe_number(complaint.get("workLossAmount"))
    time_lost = _safe_number(complaint.get("timeLostHours"))
    injury_claimed = _safe_bool(complaint.get("injuryClaimed"))
    property_damage = _safe_bool(complaint.get("propertyDamageClaimed"))
    credit_impact = _safe_bool(complaint.get("creditImpactClaimed"))
    emotional_stress = _safe_bool(complaint.get("emotionalStressClaimed"))
    short_title = complaint.get("shortTitle", "")
    what_happened = complaint.get("whatHappened", "")

    reasons: List[str] = []

    if financial_loss > 0:
        reasons.append("Financial loss alleged.")
    if work_loss > 0:
        reasons.append("Work loss alleged.")
    if time_lost > 0:
        reasons.append("Lost time alleged.")
    if injury_claimed:
        reasons.append("Personal injury alleged.")
    if property_damage:
        reasons.append("Property damage alleged.")
    if credit_impact:
        reasons.append("Credit impact alleged.")
    if emotional_stress:
        reasons.append("Emotional stress alleged.")
    if short_title or what_happened:
        reasons.append("Concrete factual narrative provided.")

    score = 0
    if financial_loss > 0:
        score += 30
    if work_loss > 0:
        score += 15
    if time_lost > 0:
        score += 10
    if injury_claimed:
        score += 20
    if property_damage:
        score += 15
    if credit_impact:
        score += 15
    if emotional_stress:
        score += 5
    if short_title or what_happened:
        score += 10

    score = min(100, score)

    if score >= 60:
        label = "strong"
    elif score >= 30:
        label = "moderate"
    elif score > 0:
        label = "weak"
    else:
        label = "missing"

    return {
        "score": score,
        "label": label,
        "reasons": reasons,
        "satisfied": score >= 30,
    }


def _derive_causation(complaint: Dict[str, Any]) -> Dict[str, Any]:
    target_name = complaint.get("targetName", "")
    target_department = complaint.get("targetDepartment", "")
    target_person = complaint.get("targetPerson", "")
    what_happened = complaint.get("whatHappened", "")
    what_was_said = complaint.get("whatWasSaid", "")
    user_actions = complaint.get("userActionsTaken", []) or []

    reasons: List[str] = []
    score = 0

    if target_name:
        reasons.append("Target entity identified.")
        score += 30
    if target_department or target_person:
        reasons.append("Specific actor or department identified.")
        score += 20
    if what_happened:
        reasons.append("Narrative connects conduct to harm.")
        score += 25
    if what_was_said:
        reasons.append("Statements or communications alleged.")
        score += 10
    if user_actions:
        reasons.append("Follow-up actions documented.")
        score += 10

    score = min(100, score)

    if score >= 60:
        label = "strong"
    elif score >= 30:
        label = "moderate"
    elif score > 0:
        label = "weak"
    else:
        label = "missing"

    return {
        "score": score,
        "label": label,
        "reasons": reasons,
        "satisfied": score >= 30,
    }


def _derive_redressability(complaint: Dict[str, Any]) -> Dict[str, Any]:
    desired_outcome = complaint.get("desiredOutcome", "")
    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    work_loss = _safe_number(complaint.get("workLossAmount"))
    prior_complaint_made = _safe_bool(complaint.get("priorComplaintMade"))

    reasons: List[str] = []
    score = 0

    if desired_outcome:
        reasons.append("Requested remedy identified.")
        score += 35
    if financial_loss > 0 or work_loss > 0:
        reasons.append("Monetary harm appears measurable.")
        score += 30
    if prior_complaint_made:
        reasons.append("Prior demand or complaint suggests relief sought is concrete.")
        score += 10

    if desired_outcome and ("payment" in desired_outcome.lower() or "refund" in desired_outcome.lower()):
        reasons.append("Requested relief appears directly tied to alleged loss.")
        score += 20

    score = min(100, score)

    if score >= 60:
        label = "strong"
    elif score >= 30:
        label = "moderate"
    elif score > 0:
        label = "weak"
    else:
        label = "missing"

    return {
        "score": score,
        "label": label,
        "reasons": reasons,
        "satisfied": score >= 30,
    }


def analyze_standing(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise StandingAnalysisServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise StandingAnalysisServiceError("No complaints found in intake_state.")

    complaint = None
    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise StandingAnalysisServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    injury = _derive_injury_in_fact(complaint)
    causation = _derive_causation(complaint)
    redressability = _derive_redressability(complaint)

    overall_score = round((injury["score"] + causation["score"] + redressability["score"]) / 3)

    if injury["satisfied"] and causation["satisfied"] and redressability["satisfied"]:
        overall_label = "standing_plausibly_supported"
    elif overall_score >= 30:
        overall_label = "standing_needs_strengthening"
    else:
        overall_label = "standing_not_yet_supported"

    next_actions: List[str] = []
    if not injury["satisfied"]:
        next_actions.append("strengthen_injury_allegations")
    if not causation["satisfied"]:
        next_actions.append("identify_actor_and_conduct")
    if not redressability["satisfied"]:
        next_actions.append("clarify_requested_relief")
    if not next_actions:
        next_actions.append("review_capacity_and_jurisdiction")

    return {
        "complaintId": complaint.get("complaintId", ""),
        "articleIIIStanding": {
            "injuryInFact": injury,
            "causation": causation,
            "redressability": redressability,
        },
        "overallStandingScore": overall_score,
        "overallStandingLabel": overall_label,
        "recommendedNextActions": next_actions,
        "note": "This is an intake-level standing screen, not legal advice or a final court determination.",
    }


if __name__ == "__main__":
    demo_state = {
        "complaintProfile": {
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "targetName": "Demo Company",
                    "targetDepartment": "Accounts Payable",
                    "shortTitle": "Unpaid work",
                    "whatHappened": "Work was completed and payment was not issued.",
                    "whatWasSaid": "Payment would be processed.",
                    "userActionsTaken": ["sent invoice", "sent follow-up"],
                    "financialLossAmount": 1200,
                    "workLossAmount": 0,
                    "timeLostHours": 4,
                    "injuryClaimed": False,
                    "propertyDamageClaimed": False,
                    "creditImpactClaimed": False,
                    "emotionalStressClaimed": False,
                    "priorComplaintMade": True,
                    "desiredOutcome": "Full payment of outstanding invoice",
                }
            ]
        }
    }

    result = analyze_standing(demo_state, "complaint-1")
    print("complaintId:", result["complaintId"])
    print("overallStandingScore:", result["overallStandingScore"])
    print("overallStandingLabel:", result["overallStandingLabel"])
    print("recommendedNextActions:", result["recommendedNextActions"])
