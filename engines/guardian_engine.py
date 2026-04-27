from typing import Any, Dict


class GuardianEngineError(Exception):
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


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def evaluate_guardian_state(intake_state: Dict[str, Any], scores: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise GuardianEngineError("intake_state must be a dictionary.")

    scores = scores or {}

    business = intake_state.get("businessProfile", {}) or {}
    compliance = intake_state.get("complianceProfile", {}) or {}
    income = intake_state.get("incomeProfile", {}) or {}
    complaint = intake_state.get("complaintProfile", {}) or {}
    evidence = intake_state.get("evidenceProfile", {}) or {}

    risk_score = _safe_number(scores.get("riskScore"))
    complaint_strength = _safe_number(scores.get("complaintStrengthScore"))
    document_readiness = _safe_number(scores.get("documentReadinessScore"))

    entity_type = business.get("entityType", "none")
    separate_bank = _safe_bool(business.get("separateBusinessBankAccount"))
    has_insurance = _safe_bool(compliance.get("hasInsurance"))
    uses_contracts = _safe_bool(compliance.get("usesWrittenContracts"))
    recordkeeping_strength = compliance.get("recordkeepingStrength", "weak")
    has_unpaid_invoices = _safe_bool(income.get("hasUnpaidInvoices"))
    has_complaint = _safe_bool(complaint.get("hasComplaintOrDispute"))
    has_evidence = _safe_bool(evidence.get("hasEvidence"))

    guardian_pressure = 0
    if risk_score >= 75:
        guardian_pressure += 35
    elif risk_score >= 50:
        guardian_pressure += 25
    elif risk_score >= 25:
        guardian_pressure += 10

    if entity_type in (None, "", "none"):
        guardian_pressure += 15
    if not separate_bank:
        guardian_pressure += 10
    if not has_insurance:
        guardian_pressure += 10
    if not uses_contracts:
        guardian_pressure += 10
    if recordkeeping_strength == "weak":
        guardian_pressure += 10
    if has_unpaid_invoices:
        guardian_pressure += 10
    if has_complaint and complaint_strength < 50:
        guardian_pressure += 10
    if has_complaint and not has_evidence:
        guardian_pressure += 10
    if document_readiness < 25:
        guardian_pressure += 5

    guardian_score = _clamp_score(guardian_pressure)

    if guardian_score >= 75:
        status = "critical"
    elif guardian_score >= 50:
        status = "warning"
    elif guardian_score >= 25:
        status = "watch"
    else:
        status = "stable"

    alerts = []
    if entity_type in (None, "", "none"):
        alerts.append("No business entity separation detected.")
    if not separate_bank:
        alerts.append("No separate business bank account detected.")
    if not has_insurance:
        alerts.append("Insurance protection not detected.")
    if not uses_contracts:
        alerts.append("Written contracts not consistently in place.")
    if has_unpaid_invoices:
        alerts.append("Outstanding revenue or unpaid invoices detected.")
    if has_complaint and not has_evidence:
        alerts.append("Complaint exists without supporting evidence.")
    if recordkeeping_strength == "weak":
        alerts.append("Recordkeeping is weak and increases exposure.")

    protective_actions = []
    if entity_type in (None, "", "none"):
        protective_actions.append("review_entity_protection")
    if not separate_bank:
        protective_actions.append("separate_finances")
    if not has_insurance:
        protective_actions.append("review_insurance_options")
    if not uses_contracts:
        protective_actions.append("activate_contract_protection")
    if has_unpaid_invoices:
        protective_actions.append("start_collections_workflow")
    if has_complaint and not has_evidence:
        protective_actions.append("collect_supporting_evidence")
    if recordkeeping_strength == "weak":
        protective_actions.append("strengthen_recordkeeping")

    escalation_triggers = []
    if guardian_score >= 75:
        escalation_triggers.append("high_exposure_state")
    if has_complaint and complaint_strength >= 50:
        escalation_triggers.append("complaint_ready_for_escalation")
    if has_unpaid_invoices:
        escalation_triggers.append("revenue_recovery_needed")

    return {
        "guardianScore": guardian_score,
        "guardianStatus": status,
        "alerts": alerts,
        "protectiveActions": protective_actions,
        "escalationTriggers": escalation_triggers,
    }


if __name__ == "__main__":
    demo_intake = {
        "businessProfile": {
            "entityType": "none",
            "separateBusinessBankAccount": False,
        },
        "complianceProfile": {
            "hasInsurance": False,
            "usesWrittenContracts": False,
            "recordkeepingStrength": "weak",
        },
        "incomeProfile": {
            "hasUnpaidInvoices": True,
        },
        "complaintProfile": {
            "hasComplaintOrDispute": True,
        },
        "evidenceProfile": {
            "hasEvidence": False,
        },
    }

    demo_scores = {
        "riskScore": 82,
        "complaintStrengthScore": 35,
        "documentReadinessScore": 20,
    }

    result = evaluate_guardian_state(demo_intake, demo_scores)
    print("guardianScore:", result["guardianScore"])
    print("guardianStatus:", result["guardianStatus"])
    print("alerts:", result["alerts"])
    print("protectiveActions:", result["protectiveActions"])
