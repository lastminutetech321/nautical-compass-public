from typing import Any, Dict


class TrustEngineError(Exception):
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


def assess_trust_readiness(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise TrustEngineError("intake_state must be a dictionary.")

    income = intake_state.get("incomeProfile", {}) or {}
    business = intake_state.get("businessProfile", {}) or {}
    compliance = intake_state.get("complianceProfile", {}) or {}
    complaint = intake_state.get("complaintProfile", {}) or {}
    evidence = intake_state.get("evidenceProfile", {}) or {}

    gross_income = _safe_number(income.get("estimatedAnnualGrossIncome"))
    net_income = _safe_number(income.get("estimatedAnnualNetIncome"))
    unpaid_invoices = _safe_bool(income.get("hasUnpaidInvoices"))

    entity_type = business.get("entityType", "none")
    separate_bank = _safe_bool(business.get("separateBusinessBankAccount"))
    operating_capacity = business.get("operatingCapacity", "individual")

    has_insurance = _safe_bool(compliance.get("hasInsurance"))
    uses_contracts = _safe_bool(compliance.get("usesWrittenContracts"))
    recordkeeping_strength = compliance.get("recordkeepingStrength", "weak")

    has_complaint = _safe_bool(complaint.get("hasComplaintOrDispute"))
    has_evidence = _safe_bool(evidence.get("hasEvidence"))

    readiness_score = 0

    if gross_income >= 150000:
        readiness_score += 30
    elif gross_income >= 100000:
        readiness_score += 24
    elif gross_income >= 70000:
        readiness_score += 18
    elif gross_income >= 40000:
        readiness_score += 10

    if net_income > 0:
        readiness_score += 8

    if entity_type not in (None, "", "none"):
        readiness_score += 12
    if separate_bank:
        readiness_score += 10
    if uses_contracts:
        readiness_score += 8
    if has_insurance:
        readiness_score += 8

    if recordkeeping_strength == "strong":
        readiness_score += 12
    elif recordkeeping_strength == "moderate":
        readiness_score += 6

    if has_complaint and has_evidence:
        readiness_score += 5
    elif has_complaint and not has_evidence:
        readiness_score -= 5

    if unpaid_invoices:
        readiness_score += 4

    readiness_score = max(0, min(100, int(round(readiness_score))))

    if readiness_score >= 75:
        readiness_band = "high"
    elif readiness_score >= 50:
        readiness_band = "moderate"
    elif readiness_score >= 25:
        readiness_band = "early"
    else:
        readiness_band = "low"

    if readiness_score >= 75 and entity_type in ("llc", "corporation", "partnership"):
        recommended_path = "trust_layer_review"
    elif readiness_score >= 50 and entity_type in (None, "", "none"):
        recommended_path = "entity_first_then_trust_review"
    elif readiness_score >= 25:
        recommended_path = "structure_foundation_first"
    else:
        recommended_path = "basic_positioning_first"

    structure_notes = []
    if entity_type in (None, "", "none"):
        structure_notes.append("No entity layer detected.")
    if not separate_bank:
        structure_notes.append("Separate banking not established.")
    if not uses_contracts:
        structure_notes.append("Contract discipline needs strengthening.")
    if not has_insurance:
        structure_notes.append("Insurance layer not present.")
    if recordkeeping_strength == "weak":
        structure_notes.append("Recordkeeping is weak for trust-level planning.")
    if has_complaint and not has_evidence:
        structure_notes.append("Complaint activity exists without evidence support.")

    trust_support_services = []

    if recommended_path == "trust_layer_review":
        trust_support_services.extend([
            "trust_preparation_packet",
            "ownership_flow_review",
            "asset_separation_support",
        ])
    elif recommended_path == "entity_first_then_trust_review":
        trust_support_services.extend([
            "entity_structure_review",
            "business_separation_setup",
            "future_trust_readiness_review",
        ])
    elif recommended_path == "structure_foundation_first":
        trust_support_services.extend([
            "recordkeeping_setup",
            "contract_protection_setup",
            "banking_separation_support",
        ])
    else:
        trust_support_services.extend([
            "basic_business_positioning",
            "intake_completion",
            "documentation_readiness",
        ])

    safeguards = []
    safeguards.append("Do not position trust support as legal advice.")
    safeguards.append("Offer preparation, structuring support, and coordination workflows.")
    safeguards.append("Final legal drafting should be handled by qualified counsel where required.")

    return {
        "trustReadinessScore": readiness_score,
        "trustReadinessBand": readiness_band,
        "recommendedPath": recommended_path,
        "operatingCapacity": operating_capacity,
        "entityType": entity_type,
        "structureNotes": structure_notes,
        "trustSupportServices": trust_support_services,
        "safeguards": safeguards,
    }


if __name__ == "__main__":
    demo_state = {
        "incomeProfile": {
            "estimatedAnnualGrossIncome": 120000,
            "estimatedAnnualNetIncome": 85000,
            "hasUnpaidInvoices": True,
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

    result = assess_trust_readiness(demo_state)
    print("trustReadinessScore:", result["trustReadinessScore"])
    print("trustReadinessBand:", result["trustReadinessBand"])
    print("recommendedPath:", result["recommendedPath"])
    print("trustSupportServices:", result["trustSupportServices"])
