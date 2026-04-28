from typing import Any, Dict

from runtime.helm_state_adapter import build_helm_state


class HelmServiceError(Exception):
    pass


def get_helm_state(
    intake_state: Dict[str, Any],
    scores: Dict[str, Any],
    routes: Dict[str, Any],
    document_history: list[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise HelmServiceError("intake_state must be a dictionary.")
    if not isinstance(scores, dict):
        raise HelmServiceError("scores must be a dictionary.")
    if not isinstance(routes, dict):
        raise HelmServiceError("routes must be a dictionary.")

    return build_helm_state(
        intake_state=intake_state,
        scores=scores,
        routes=routes,
        document_history=document_history or [],
    )


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

    helm = get_helm_state(demo_intake, demo_scores, demo_routes, demo_history)

    print("globalAlertState:", helm["globalAlertState"])
    print("riskIndex:", helm["gauges"]["riskIndex"])
    print("recommendedModules:", helm["summary"]["recommendedModules"])
    print("nextBestActions:", helm["summary"]["nextBestActions"])
