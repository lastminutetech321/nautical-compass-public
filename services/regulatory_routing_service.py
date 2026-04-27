from typing import Any, Dict, List


class RegulatoryRoutingServiceError(Exception):
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


def _derive_regulatory_routes(intake_state: Dict[str, Any], complaint: Dict[str, Any]) -> Dict[str, Any]:
    target_type = _normalize_target_type(complaint)

    category = (complaint.get("category", "") or "").lower()
    subcategory = (complaint.get("subcategory", "") or "").lower()
    short_title = (complaint.get("shortTitle", "") or "").lower()
    summary = (complaint.get("plainLanguageSummary", "") or "").lower()
    happened = (complaint.get("whatHappened", "") or "").lower()
    desired_outcome = (complaint.get("desiredOutcome", "") or "").lower()

    text = " ".join([category, subcategory, short_title, summary, happened, desired_outcome])

    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    credit_impact = _safe_bool(complaint.get("creditImpactClaimed"))
    has_evidence = _safe_bool(intake_state.get("evidenceProfile", {}).get("hasEvidence"))
    has_complaint = _safe_bool(intake_state.get("complaintProfile", {}).get("hasComplaintOrDispute"))

    routes: List[Dict[str, str]] = []
    reasons: List[str] = []

    def add_route(code: str, label: str, basis: str) -> None:
        for item in routes:
            if item["code"] == code:
                return
        routes.append({"code": code, "label": label, "basis": basis})

    if target_type == "government":
        add_route("internal_public_complaint", "Internal Public Complaint", "Government target suggests internal or oversight complaint path.")
        reasons.append("Government target detected.")

        if any(term in text for term in ["police", "officer", "detained", "searched", "arrested", "retaliation"]):
            add_route("civil_rights_oversight", "Civil Rights / Oversight Review", "Public-force or retaliation language detected.")
            reasons.append("Civil-rights style public-actor language detected.")

    if any(term in text for term in ["credit", "report", "bureau", "score"]):
        add_route("consumer_credit_regulator", "Consumer Credit Regulator Review", "Credit-reporting language detected.")
        reasons.append("Credit-impact language detected.")

    if any(term in text for term in ["debt", "collector", "collection", "harassment"]):
        add_route("debt_collection_regulator", "Debt Collection Regulator Review", "Debt-collection language detected.")
        reasons.append("Debt-collection language detected.")

    if any(term in text for term in ["payment", "invoice", "refund", "contract", "nonpayment", "breach"]):
        add_route("commercial_or_consumer_dispute", "Commercial / Consumer Dispute Review", "Payment or contract dispute language detected.")
        reasons.append("Payment, invoice, refund, or contract language detected.")

    if any(term in text for term in ["unsafe", "hazard", "injury", "osha", "worksite"]):
        add_route("safety_regulator_review", "Safety / Workplace Regulator Review", "Safety or worksite hazard language detected.")
        reasons.append("Safety or workplace hazard language detected.")

    if credit_impact:
        reasons.append("Credit impact alleged.")
    if financial_loss > 0:
        reasons.append("Monetary loss alleged.")
    if has_complaint and not has_evidence:
        reasons.append("Complaint exists but evidence support is incomplete.")
    elif has_evidence:
        reasons.append("Evidence support is present for routing review.")

    if not routes:
        add_route("general_regulatory_screen", "General Regulatory Screen", "Fact pattern needs more specific routing.")
        reasons.append("No specialized route triggered yet.")

    if len(routes) >= 3:
        routing_strength = "multi_route"
    elif len(routes) == 2:
        routing_strength = "moderate_route"
    else:
        routing_strength = "single_route"

    return {
        "targetType": target_type,
        "routes": routes,
        "reasons": reasons,
        "routingStrength": routing_strength,
    }


def analyze_regulatory_routes(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise RegulatoryRoutingServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise RegulatoryRoutingServiceError("No complaints found in intake_state.")

    complaint = None
    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise RegulatoryRoutingServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    analysis = _derive_regulatory_routes(intake_state, complaint)

    next_actions: List[str] = []
    route_codes = [route["code"] for route in analysis["routes"]]

    if "consumer_credit_regulator" in route_codes:
        next_actions.append("prepare_consumer_credit_packet")
    if "debt_collection_regulator" in route_codes:
        next_actions.append("prepare_debt_collection_packet")
    if "civil_rights_oversight" in route_codes:
        next_actions.append("prepare_civil_rights_oversight_packet")
    if "safety_regulator_review" in route_codes:
        next_actions.append("prepare_safety_packet")
    if "commercial_or_consumer_dispute" in route_codes:
        next_actions.append("prepare_demand_and_dispute_packet")
    if "general_regulatory_screen" in route_codes:
        next_actions.append("clarify_regulatory_target")

    if not next_actions:
        next_actions.append("review_best_regulatory_forum")

    return {
        "complaintId": complaint.get("complaintId", ""),
        "targetName": complaint.get("targetName", ""),
        "regulatoryRouting": analysis,
        "recommendedNextActions": next_actions,
        "note": "This is an intake-level regulatory routing screen, not legal advice or a final filing recommendation.",
    }


if __name__ == "__main__":
    demo_state = {
        "complaintProfile": {
            "hasComplaintOrDispute": True,
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "targetType": "private",
                    "targetName": "Demo Collections LLC",
                    "category": "debt_issue",
                    "shortTitle": "Debt harassment and credit reporting",
                    "plainLanguageSummary": "Collector harassed me and reported inaccurate debt information.",
                    "whatHappened": "Repeated collection calls and credit report damage.",
                    "desiredOutcome": "Correction and damages",
                    "financialLossAmount": 900,
                    "creditImpactClaimed": True,
                }
            ],
        },
        "evidenceProfile": {
            "hasEvidence": True,
        },
    }

    result = analyze_regulatory_routes(demo_state, "complaint-1")
    print("complaintId:", result["complaintId"])
    print("routingStrength:", result["regulatoryRouting"]["routingStrength"])
    print("routes:", result["regulatoryRouting"]["routes"])
    print("recommendedNextActions:", result["recommendedNextActions"])
