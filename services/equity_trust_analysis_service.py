from typing import Any, Dict, List

from engines.equity_engine import analyze_equity_position
from engines.trust_engine import assess_trust_readiness


class EquityTrustAnalysisServiceError(Exception):
    pass


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_equity_trust_analysis(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise EquityTrustAnalysisServiceError("intake_state must be a dictionary.")

    equity = analyze_equity_position(intake_state)
    trust = assess_trust_readiness(intake_state)

    savings_score = equity.get("scores", {}).get("savingsOpportunityScore", 0)
    trust_score = trust.get("trustReadinessScore", 0)
    positioning_band = equity.get("positioningBand", "unknown")
    trust_band = trust.get("trustReadinessBand", "low")

    overall_label = "basic_positioning_review"

    if savings_score >= 70 and trust_score >= 60:
        overall_label = "equity_and_trust_expansion_candidate"
    elif savings_score >= 70:
        overall_label = "equity_optimization_candidate"
    elif trust_score >= 60:
        overall_label = "trust_structure_candidate"
    elif savings_score >= 40 or trust_score >= 30:
        overall_label = "structure_foundation_candidate"

    recommended_next_actions = _dedupe(
        equity.get("priorityActions", [])
        + trust.get("trustSupportServices", [])
    )

    return {
        "overallEquityTrustLabel": overall_label,
        "equitySummary": {
            "positioningBand": positioning_band,
            "recommendedStructure": equity.get("recommendedStructure"),
            "scores": equity.get("scores", {}),
            "equityLeakPoints": equity.get("equityLeakPoints", []),
            "priorityActions": equity.get("priorityActions", []),
        },
        "trustSummary": {
            "trustReadinessScore": trust_score,
            "trustReadinessBand": trust_band,
            "recommendedPath": trust.get("recommendedPath"),
            "entityType": trust.get("entityType"),
            "operatingCapacity": trust.get("operatingCapacity"),
            "structureNotes": trust.get("structureNotes", []),
            "trustSupportServices": trust.get("trustSupportServices", []),
            "safeguards": trust.get("safeguards", []),
        },
        "recommendedNextActions": recommended_next_actions,
        "message": "Equity and trust analysis ready",
    }


if __name__ == "__main__":
    demo_state = {
        "incomeProfile": {
            "estimatedAnnualGrossIncome": 120000,
            "estimatedAnnualNetIncome": 85000,
            "hasUnpaidInvoices": True,
        },
        "expenseProfile": {
            "estimatedAnnualBusinessExpenses": 0,
            "tracksMileage": False,
        },
        "businessProfile": {
            "entityType": "llc",
            "separateBusinessBankAccount": True,
            "operatingCapacity": "business_entity",
        },
        "complianceProfile": {
            "hasInsurance": False,
            "usesWrittenContracts": True,
            "recordkeepingStrength": "moderate",
        },
        "complaintProfile": {
            "hasComplaintOrDispute": False,
        },
        "evidenceProfile": {
            "hasEvidence": False,
        },
    }

    result = build_equity_trust_analysis(demo_state)
    print("message:", result["message"])
    print("overallEquityTrustLabel:", result["overallEquityTrustLabel"])
    print("positioningBand:", result["equitySummary"]["positioningBand"])
    print("trustReadinessBand:", result["trustSummary"]["trustReadinessBand"])
    print("recommendedNextActions:", result["recommendedNextActions"])
