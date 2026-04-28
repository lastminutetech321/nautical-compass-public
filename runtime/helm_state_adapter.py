from typing import Any, Dict, List


class HelmStateError(Exception):
    pass


def _safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _count_missing_core_fields(intake_state: Dict[str, Any]) -> int:
    missing = 0

    checks = [
        intake_state.get("identityProfile", {}).get("fullLegalName"),
        intake_state.get("identityProfile", {}).get("email"),
        intake_state.get("identityProfile", {}).get("phone"),
        intake_state.get("identityProfile", {}).get("residentialAddress", {}).get("street1"),
        intake_state.get("identityProfile", {}).get("residentialAddress", {}).get("city"),
        intake_state.get("identityProfile", {}).get("residentialAddress", {}).get("state"),
        intake_state.get("identityProfile", {}).get("residentialAddress", {}).get("postalCode"),
        intake_state.get("workProfile", {}).get("workerType"),
        intake_state.get("incomeProfile", {}).get("estimatedAnnualGrossIncome"),
    ]

    for value in checks:
        if value in (None, "", []):
            missing += 1

    return missing


def _build_gauge(score: int, label: str, subtitle: str) -> Dict[str, Any]:
    return {
        "score": max(0, min(100, score)),
        "label": label,
        "subtitle": subtitle,
    }


def build_helm_state(
    intake_state: Dict[str, Any],
    scores: Dict[str, Any],
    routes: Dict[str, Any],
    document_history: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise HelmStateError("intake_state must be a dictionary.")
    if not isinstance(scores, dict):
        raise HelmStateError("scores must be a dictionary.")
    if not isinstance(routes, dict):
        raise HelmStateError("routes must be a dictionary.")

    document_history = document_history or []

    risk_score = _safe_int(scores.get("riskScore"))
    savings_score = _safe_int(scores.get("savingsOpportunityScore"))
    complaint_score = _safe_int(scores.get("complaintStrengthScore"))
    entity_score = _safe_int(scores.get("entityReadinessScore"))
    document_score = _safe_int(scores.get("documentReadinessScore"))
    classification_score = _safe_int(scores.get("classificationScore"))

    recommended_modules = routes.get("recommendedModules", []) or []
    priority_actions = routes.get("priorityActions", []) or []
    blocked_actions = routes.get("blockedActions", []) or []

    has_complaint = bool(intake_state.get("complaintProfile", {}).get("hasComplaintOrDispute"))
    unpaid_invoices = bool(intake_state.get("incomeProfile", {}).get("hasUnpaidInvoices"))
    completion_percent = _safe_int(intake_state.get("completionPercent"))
    missing_core_fields = _count_missing_core_fields(intake_state)

    flow_score = min(100, int((savings_score * 0.6) + (classification_score * 0.2) + (document_score * 0.2)))
    signal_score = min(100, int((complaint_score * 0.6) + (len(recommended_modules) * 10) + (len(priority_actions) * 5)))
    direction_score = min(100, int((entity_score * 0.5) + (savings_score * 0.3) + (classification_score * 0.2)))
    velocity_score = min(100, int((completion_percent * 0.6) + (document_score * 0.4)))

    system_load_raw = (missing_core_fields * 10) + (len(priority_actions) * 10) + (10 if unpaid_invoices else 0) + (10 if has_complaint else 0)
    system_load_score = min(100, system_load_raw)

    if risk_score >= 75:
        global_alert_state = "critical"
    elif risk_score >= 50:
        global_alert_state = "warning"
    elif risk_score >= 25:
        global_alert_state = "watch"
    else:
        global_alert_state = "stable"

    risk_label = scores.get("riskLabel", "unknown")
    flow_label = "surging" if flow_score >= 75 else "strong" if flow_score >= 50 else "steady" if flow_score >= 25 else "weak"
    signal_label = "high_traffic" if signal_score >= 75 else "strong" if signal_score >= 50 else "active" if signal_score >= 25 else "quiet"
    direction_label = scores.get("overallPositionLabel", "early_stage")
    velocity_label = "fast" if velocity_score >= 75 else "moving" if velocity_score >= 50 else "slow" if velocity_score >= 25 else "stalled"
    system_load_label = "critical" if system_load_score >= 75 else "high" if system_load_score >= 50 else "moderate" if system_load_score >= 25 else "low"

    next_best_actions = []
    next_best_actions.extend(priority_actions[:3])

    if document_score < 50:
        next_best_actions.append("complete_intake")
    if risk_score >= 50 and "review_structure_risk" not in next_best_actions:
        next_best_actions.append("review_structure_risk")
    if len(document_history) == 0:
        next_best_actions.append("generate_first_document")

    deduped_actions = []
    for action in next_best_actions:
        if action not in deduped_actions:
            deduped_actions.append(action)

    return {
        "globalAlertState": global_alert_state,
        "gauges": {
            "riskIndex": _build_gauge(risk_score, risk_label, "Legal, structural, and operational exposure"),
            "flow": _build_gauge(flow_score, flow_label, "Opportunity, savings, and output potential"),
            "signal": _build_gauge(signal_score, signal_label, "Complaint strength and active routes"),
            "direction": _build_gauge(direction_score, direction_label, "Position and next-stage direction"),
            "velocity": _build_gauge(velocity_score, velocity_label, "Progress toward usable outputs"),
            "systemLoad": _build_gauge(system_load_score, system_load_label, "Missing fields, pending actions, and pressure"),
        },
        "summary": {
            "recommendedModules": recommended_modules,
            "blockedActions": blocked_actions,
            "priorityActions": priority_actions,
            "nextBestActions": deduped_actions,
            "documentHistoryCount": len(document_history),
            "completionPercent": completion_percent,
        },
    }


if __name__ == "__main__":
    demo_intake = {
        "completionPercent": 80,
        "identityProfile": {
            "fullLegalName": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-123-4567",
            "residentialAddress": {
                "street1": "123 Harbor Way",
                "city": "Baltimore",
                "state": "MD",
                "postalCode": "21201",
            },
        },
        "workProfile": {
            "workerType": "independent_contractor",
        },
        "incomeProfile": {
            "estimatedAnnualGrossIncome": 85000,
            "hasUnpaidInvoices": True,
        },
        "complaintProfile": {
            "hasComplaintOrDispute": True,
        },
    }

    demo_scores = {
        "classificationScore": 80,
        "savingsOpportunityScore": 93,
        "riskScore": 90,
        "complaintStrengthScore": 55,
        "documentReadinessScore": 60,
        "entityReadinessScore": 25,
        "riskLabel": "critical",
        "overallPositionLabel": "high_exposure",
    }

    demo_routes = {
        "recommendedModules": ["tax_positioning", "invoice_ops", "complaint_curation"],
        "priorityActions": ["review_deductions", "generate_invoice", "generate_complaint_summary"],
        "blockedActions": [],
    }

    demo_history = [
        {"documentType": "w9", "status": "generated"}
    ]

    helm_state = build_helm_state(demo_intake, demo_scores, demo_routes, demo_history)
    print("globalAlertState:", helm_state["globalAlertState"])
    print("riskIndex:", helm_state["gauges"]["riskIndex"])
    print("flow:", helm_state["gauges"]["flow"])
    print("nextBestActions:", helm_state["summary"]["nextBestActions"])
