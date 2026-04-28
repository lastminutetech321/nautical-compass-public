from typing import Any, Dict, List


class RightsViolationServiceError(Exception):
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


def _derive_rights_flags(complaint: Dict[str, Any]) -> Dict[str, Any]:
    target_type = _normalize_target_type(complaint)

    category = (complaint.get("category", "") or "").lower()
    subcategory = (complaint.get("subcategory", "") or "").lower()
    short_title = (complaint.get("shortTitle", "") or "").lower()
    summary = (complaint.get("plainLanguageSummary", "") or "").lower()
    happened = (complaint.get("whatHappened", "") or "").lower()
    said = (complaint.get("whatWasSaid", "") or "").lower()
    desired_outcome = (complaint.get("desiredOutcome", "") or "").lower()

    text = " ".join([category, subcategory, short_title, summary, happened, said, desired_outcome])

    rights_flags: List[Dict[str, str]] = []
    reasons: List[str] = []

    def add_flag(code: str, label: str, basis: str) -> None:
        for item in rights_flags:
            if item["code"] == code:
                return
        rights_flags.append({"code": code, "label": label, "basis": basis})

    if target_type == "government":
        if any(term in text for term in ["search", "seizure", "stop", "detained", "arrested", "property taken"]):
            add_flag("fourth_amendment", "Search / Seizure / Detention", "Fact pattern suggests public-force or seizure conduct.")
            reasons.append("Search, seizure, detention, or arrest language detected.")

        if any(term in text for term in ["due process", "hearing", "notice", "deprived", "policy", "license", "benefit"]):
            add_flag("fourteenth_amendment_due_process", "Due Process", "Possible deprivation without adequate process.")
            reasons.append("Process-related deprivation language detected.")

        if any(term in text for term in ["discrimination", "unequal", "selective", "targeted", "race", "class"]):
            add_flag("fourteenth_amendment_equal_protection", "Equal Protection", "Possible unequal treatment by public actor.")
            reasons.append("Discrimination or unequal-treatment language detected.")

        if any(term in text for term in ["speech", "retaliation", "petition", "complaint", "protest"]):
            add_flag("first_amendment", "Speech / Petition / Retaliation", "Possible retaliation tied to protected expression.")
            reasons.append("Speech, complaint, petition, or retaliation language detected.")

        if any(term in text for term in ["civil rights", "constitutional", "rights violated"]):
            add_flag("section_1983_path", "Potential §1983 Path", "Public actor + rights language may support civil-rights review.")
            reasons.append("Civil-rights or constitutional language detected against public actor.")

    if target_type == "private":
        if any(term in text for term in ["credit", "reporting", "consumer report", "score", "bureau"]):
            add_flag("consumer_credit_issue", "Consumer Credit Issue", "Credit-related private dispute detected.")
            reasons.append("Credit-reporting or credit-impact language detected.")

        if any(term in text for term in ["debt", "collection", "collector", "harassment", "owed"]):
            add_flag("debt_collection_issue", "Debt Collection Issue", "Debt-collection fact pattern detected.")
            reasons.append("Debt-collection language detected.")

        if any(term in text for term in ["payment", "invoice", "contract", "breach", "nonpayment", "refund"]):
            add_flag("contract_or_receivables_issue", "Contract / Receivables Issue", "Private payment or contract dispute detected.")
            reasons.append("Payment, invoice, refund, or contract language detected.")

    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    injury_claimed = _safe_bool(complaint.get("injuryClaimed"))
    property_damage = _safe_bool(complaint.get("propertyDamageClaimed"))
    credit_impact = _safe_bool(complaint.get("creditImpactClaimed"))

    if financial_loss > 0:
        reasons.append("Measurable financial harm alleged.")
    if injury_claimed:
        reasons.append("Personal injury alleged.")
    if property_damage:
        reasons.append("Property damage alleged.")
    if credit_impact:
        reasons.append("Credit impact alleged.")

    severity_score = 0
    severity_score += min(40, len(rights_flags) * 15)
    if financial_loss > 0:
        severity_score += 15
    if injury_claimed:
        severity_score += 20
    if property_damage:
        severity_score += 10
    if credit_impact:
        severity_score += 10

    severity_score = min(100, severity_score)

    if severity_score >= 60:
        severity_label = "strong_issue_signal"
    elif severity_score >= 30:
        severity_label = "moderate_issue_signal"
    elif severity_score > 0:
        severity_label = "weak_issue_signal"
    else:
        severity_label = "unclear_issue_signal"

    return {
        "targetType": target_type,
        "rightsFlags": rights_flags,
        "reasons": reasons,
        "severityScore": severity_score,
        "severityLabel": severity_label,
    }


def analyze_rights_violations(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise RightsViolationServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise RightsViolationServiceError("No complaints found in intake_state.")

    complaint = None
    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise RightsViolationServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    analysis = _derive_rights_flags(complaint)
    target_type = analysis["targetType"]
    flags = analysis["rightsFlags"]

    next_actions: List[str] = []

    if not flags:
        next_actions.append("clarify_fact_pattern")
        next_actions.append("identify_applicable_right_or_claim")
    else:
        if target_type == "government":
            next_actions.append("review_public_actor_claim_path")
            if any(flag["code"] == "section_1983_path" for flag in flags):
                next_actions.append("review_section_1983_route")
        else:
            next_actions.append("review_private_actor_statute_or_contract_path")

        if any(flag["code"] == "consumer_credit_issue" for flag in flags):
            next_actions.append("review_consumer_credit_path")
        if any(flag["code"] == "debt_collection_issue" for flag in flags):
            next_actions.append("review_debt_collection_path")
        if any(flag["code"] == "contract_or_receivables_issue" for flag in flags):
            next_actions.append("review_contract_and_receivables_path")

    return {
        "complaintId": complaint.get("complaintId", ""),
        "targetName": complaint.get("targetName", ""),
        "rightsAnalysis": analysis,
        "recommendedNextActions": next_actions,
        "note": "This is an intake-level rights and claim-spotting screen, not legal advice or a final merits determination.",
    }


if __name__ == "__main__":
    demo_state = {
        "complaintProfile": {
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "targetType": "government",
                    "targetName": "City Police Department",
                    "category": "civil_rights",
                    "shortTitle": "Unlawful stop and retaliation",
                    "plainLanguageSummary": "I was stopped, detained, and retaliated against after making a complaint.",
                    "whatHappened": "Officer stopped me, detained me, searched my property, and threatened me after I protested.",
                    "whatWasSaid": "They told me to stop complaining.",
                    "desiredOutcome": "Injunction and damages",
                    "financialLossAmount": 1200,
                    "injuryClaimed": True,
                    "propertyDamageClaimed": False,
                    "creditImpactClaimed": False,
                }
            ]
        }
    }

    result = analyze_rights_violations(demo_state, "complaint-1")
    print("complaintId:", result["complaintId"])
    print("severityLabel:", result["rightsAnalysis"]["severityLabel"])
    print("rightsFlags:", result["rightsAnalysis"]["rightsFlags"])
    print("recommendedNextActions:", result["recommendedNextActions"])
