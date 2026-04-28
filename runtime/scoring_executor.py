from typing import Any, Dict

from utils.spec_loader import load_spec


class ScoringError(Exception):
    pass


def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if "[" in part and "]" in part:
            prefix = part[: part.index("[")]
            index_str = part[part.index("[") + 1 : part.index("]")]
            if prefix:
                if not isinstance(current, dict) or prefix not in current:
                    return None
                current = current[prefix]
            if not isinstance(current, list) or not index_str.isdigit():
                return None
            index = int(index_str)
            if index >= len(current):
                return None
            current = current[index]
            suffix = part[part.index("]") + 1 :]
            if suffix:
                if suffix.startswith("."):
                    suffix = suffix[1:]
                if suffix:
                    if not isinstance(current, dict) or suffix not in current:
                        return None
                    current = current[suffix]
        else:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
    return current


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _safe_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _label_from_score(score: int, mapping: Dict[str, str]) -> str:
    if 0 <= score <= 24:
        return mapping.get("0-24", "unknown")
    if 25 <= score <= 49:
        return mapping.get("25-49", "unknown")
    if 50 <= score <= 74:
        return mapping.get("50-74", "unknown")
    return mapping.get("75-100", "unknown")


def _compute_classification_score(intake_state: Dict[str, Any]) -> int:
    score = 0

    worker_type = _get_nested_value(intake_state, "workProfile.workerType")
    receives_w2 = _safe_bool(_get_nested_value(intake_state, "incomeProfile.receivesW2"))
    receives_1099 = _safe_bool(_get_nested_value(intake_state, "incomeProfile.receives1099"))
    sets_own_schedule = _safe_bool(_get_nested_value(intake_state, "workProfile.setsOwnSchedule"))
    provides_own_tools = _safe_bool(_get_nested_value(intake_state, "workProfile.providesOwnTools"))
    operating_capacity = _get_nested_value(intake_state, "businessProfile.operatingCapacity")
    entity_type = _get_nested_value(intake_state, "businessProfile.entityType")

    if worker_type and worker_type != "unknown":
        score += 25
    if receives_w2 or receives_1099:
        score += 20
    if receives_w2 and receives_1099:
        score += 10
    if sets_own_schedule:
        score += 15
    if provides_own_tools:
        score += 10
    if operating_capacity and operating_capacity != "unknown":
        score += 10
    if entity_type and entity_type != "none":
        score += 10

    return _clamp_score(score)


def _compute_savings_opportunity_score(intake_state: Dict[str, Any]) -> int:
    score = 0

    gross_income = _safe_number(_get_nested_value(intake_state, "incomeProfile.estimatedAnnualGrossIncome"))
    net_income = _safe_number(_get_nested_value(intake_state, "incomeProfile.estimatedAnnualNetIncome"))
    expenses = _safe_number(_get_nested_value(intake_state, "expenseProfile.estimatedAnnualBusinessExpenses"))
    tracks_mileage = _safe_bool(_get_nested_value(intake_state, "expenseProfile.tracksMileage"))
    recordkeeping = _get_nested_value(intake_state, "complianceProfile.recordkeepingStrength")
    entity_type = _get_nested_value(intake_state, "businessProfile.entityType")
    separate_bank = _safe_bool(_get_nested_value(intake_state, "businessProfile.separateBusinessBankAccount"))

    if gross_income >= 100000:
        score += 35
    elif gross_income >= 70000:
        score += 28
    elif gross_income >= 40000:
        score += 20
    elif gross_income > 0:
        score += 10

    if net_income > 0:
        score += 10

    if expenses == 0 and gross_income > 0:
        score += 15
    elif expenses > 0:
        score += 5

    if not tracks_mileage:
        score += 10

    if recordkeeping == "weak":
        score += 15
    elif recordkeeping == "moderate":
        score += 8

    if entity_type in (None, "", "none"):
        score += 10

    if not separate_bank:
        score += 5

    return _clamp_score(score)


def _compute_risk_score(intake_state: Dict[str, Any]) -> int:
    score = 0

    entity_type = _get_nested_value(intake_state, "businessProfile.entityType")
    separate_bank = _safe_bool(_get_nested_value(intake_state, "businessProfile.separateBusinessBankAccount"))
    has_insurance = _safe_bool(_get_nested_value(intake_state, "complianceProfile.hasInsurance"))
    uses_contracts = _safe_bool(_get_nested_value(intake_state, "complianceProfile.usesWrittenContracts"))
    recordkeeping = _get_nested_value(intake_state, "complianceProfile.recordkeepingStrength")
    has_unpaid_invoices = _safe_bool(_get_nested_value(intake_state, "incomeProfile.hasUnpaidInvoices"))
    has_complaint = _safe_bool(_get_nested_value(intake_state, "complaintProfile.hasComplaintOrDispute"))

    if entity_type in (None, "", "none"):
        score += 25
    if not separate_bank:
        score += 15
    if not has_insurance:
        score += 15
    if not uses_contracts:
        score += 15
    if recordkeeping == "weak":
        score += 10
    elif recordkeeping == "moderate":
        score += 5
    if has_unpaid_invoices:
        score += 10
    if has_complaint:
        score += 10

    return _clamp_score(score)


def _compute_complaint_strength_score(intake_state: Dict[str, Any]) -> int:
    score = 0

    complaints = _get_nested_value(intake_state, "complaintProfile.complaints")
    if not isinstance(complaints, list) or len(complaints) == 0:
        return 0

    complaint = complaints[0] or {}

    if complaint.get("shortTitle"):
        score += 10
    if complaint.get("plainLanguageSummary"):
        score += 20
    if complaint.get("whatHappened"):
        score += 20
    if complaint.get("targetName"):
        score += 10
    if complaint.get("harmTypes"):
        score += 10

    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    if financial_loss > 0:
        score += 10

    timeline_events = complaint.get("timelineEvents", [])
    if isinstance(timeline_events, list) and len(timeline_events) > 0:
        score += 10

    related_evidence_ids = complaint.get("relatedEvidenceIds", [])
    if isinstance(related_evidence_ids, list) and len(related_evidence_ids) > 0:
        score += 10

    return _clamp_score(score)


def _compute_document_readiness_score(intake_state: Dict[str, Any]) -> int:
    score = 0

    w9_ready = _safe_bool(_get_nested_value(intake_state, "documentProfile.w9Ready"))
    invoice_ready = _safe_bool(_get_nested_value(intake_state, "documentProfile.invoiceReady"))
    contractor_ready = _safe_bool(_get_nested_value(intake_state, "documentProfile.contractorProfileReady"))

    full_name = _get_nested_value(intake_state, "identityProfile.fullLegalName")
    email = _get_nested_value(intake_state, "identityProfile.email")
    phone = _get_nested_value(intake_state, "identityProfile.phone")
    business_name = _get_nested_value(intake_state, "businessProfile.businessName")

    if full_name:
        score += 20
    if email:
        score += 15
    if phone:
        score += 15
    if business_name:
        score += 10

    if w9_ready:
        score += 15
    if invoice_ready:
        score += 15
    if contractor_ready:
        score += 10

    return _clamp_score(score)


def _compute_entity_readiness_score(intake_state: Dict[str, Any]) -> int:
    score = 0

    gross_income = _safe_number(_get_nested_value(intake_state, "incomeProfile.estimatedAnnualGrossIncome"))
    entity_type = _get_nested_value(intake_state, "businessProfile.entityType")
    separate_bank = _safe_bool(_get_nested_value(intake_state, "businessProfile.separateBusinessBankAccount"))
    recordkeeping = _get_nested_value(intake_state, "complianceProfile.recordkeepingStrength")
    uses_contracts = _safe_bool(_get_nested_value(intake_state, "complianceProfile.usesWrittenContracts"))
    has_insurance = _safe_bool(_get_nested_value(intake_state, "complianceProfile.hasInsurance"))

    if gross_income >= 100000:
        score += 30
    elif gross_income >= 70000:
        score += 25
    elif gross_income >= 40000:
        score += 15
    elif gross_income > 0:
        score += 5

    if entity_type not in (None, "", "none"):
        score += 20
    if separate_bank:
        score += 15
    if recordkeeping == "strong":
        score += 15
    elif recordkeeping == "moderate":
        score += 8
    if uses_contracts:
        score += 10
    if has_insurance:
        score += 10

    return _clamp_score(score)


def compute_overall_position(scores: Dict[str, int]) -> str:
    risk = scores.get("riskScore", 0)
    complaint = scores.get("complaintStrengthScore", 0)
    entity = scores.get("entityReadinessScore", 0)
    savings = scores.get("savingsOpportunityScore", 0)

    if risk >= 75:
        return "high_exposure"
    if complaint >= 50:
        return "complaint_ready"
    if entity >= 75 and savings >= 50:
        return "growth_ready"
    if risk >= 50:
        return "unprotected_operator"
    if entity >= 40:
        return "developing_business"
    return "early_stage"


def compute_scores(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ScoringError("intake_state must be a dictionary.")

    spec = load_spec("scoring_engine_spec")
    labels = spec.get("scoringEngine", {}).get("labels", {})

    classification_score = _compute_classification_score(intake_state)
    savings_score = _compute_savings_opportunity_score(intake_state)
    risk_score = _compute_risk_score(intake_state)
    complaint_score = _compute_complaint_strength_score(intake_state)
    document_score = _compute_document_readiness_score(intake_state)
    entity_score = _compute_entity_readiness_score(intake_state)

    score_values = {
        "classificationScore": classification_score,
        "savingsOpportunityScore": savings_score,
        "riskScore": risk_score,
        "complaintStrengthScore": complaint_score,
        "documentReadinessScore": document_score,
        "entityReadinessScore": entity_score,
    }

    result = {
        **score_values,
        "classificationLabel": _label_from_score(classification_score, labels.get("classificationScore", {})),
        "savingsOpportunityLabel": _label_from_score(savings_score, labels.get("savingsOpportunityScore", {})),
        "riskLabel": _label_from_score(risk_score, labels.get("riskScore", {})),
        "complaintStrengthLabel": _label_from_score(complaint_score, labels.get("complaintStrengthScore", {})),
        "documentReadinessLabel": _label_from_score(document_score, labels.get("documentReadinessScore", {})),
        "entityReadinessLabel": _label_from_score(entity_score, labels.get("entityReadinessScore", {})),
    }

    result["overallPositionLabel"] = compute_overall_position(score_values)
    return result


if __name__ == "__main__":
    demo_state = load_spec("master_intake_schema")

    demo_state["identityProfile"]["fullLegalName"] = "Jane Doe"
    demo_state["identityProfile"]["email"] = "jane@example.com"
    demo_state["identityProfile"]["phone"] = "555-123-4567"
    demo_state["businessProfile"]["businessName"] = "Doe Services"
    demo_state["businessProfile"]["entityType"] = "none"
    demo_state["businessProfile"]["separateBusinessBankAccount"] = False
    demo_state["workProfile"]["workerType"] = "independent_contractor"
    demo_state["workProfile"]["setsOwnSchedule"] = True
    demo_state["workProfile"]["providesOwnTools"] = True
    demo_state["incomeProfile"]["receives1099"] = True
    demo_state["incomeProfile"]["estimatedAnnualGrossIncome"] = 85000
    demo_state["incomeProfile"]["estimatedAnnualNetIncome"] = 65000
    demo_state["incomeProfile"]["hasUnpaidInvoices"] = True
    demo_state["expenseProfile"]["tracksMileage"] = False
    demo_state["expenseProfile"]["estimatedAnnualBusinessExpenses"] = 0
    demo_state["complianceProfile"]["recordkeepingStrength"] = "weak"
    demo_state["complianceProfile"]["hasInsurance"] = False
    demo_state["complianceProfile"]["usesWrittenContracts"] = False

    scores = compute_scores(demo_state)
    for key, value in scores.items():
        print(f"{key}: {value}")
