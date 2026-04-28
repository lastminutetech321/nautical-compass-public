from typing import Any, Dict

from runtime.scoring_executor import compute_scores
from runtime.routing_executor import compute_routes


class ResultsServiceError(Exception):
    pass


def build_results_summary(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ResultsServiceError("intake_state must be a dictionary.")

    scores = compute_scores(intake_state)
    routes = compute_routes(intake_state, scores)

    return {
        "classification": {
            "score": scores.get("classificationScore"),
            "label": scores.get("classificationLabel"),
        },
        "savingsOpportunity": {
            "score": scores.get("savingsOpportunityScore"),
            "label": scores.get("savingsOpportunityLabel"),
        },
        "risk": {
            "score": scores.get("riskScore"),
            "label": scores.get("riskLabel"),
        },
        "complaintStrength": {
            "score": scores.get("complaintStrengthScore"),
            "label": scores.get("complaintStrengthLabel"),
        },
        "documentReadiness": {
            "score": scores.get("documentReadinessScore"),
            "label": scores.get("documentReadinessLabel"),
        },
        "entityReadiness": {
            "score": scores.get("entityReadinessScore"),
            "label": scores.get("entityReadinessLabel"),
        },
        "overallPositionLabel": scores.get("overallPositionLabel"),
        "recommendedModules": routes.get("recommendedModules", []),
        "upgradePaths": routes.get("upgradePaths", []),
        "priorityActions": routes.get("priorityActions", []),
        "blockedActions": routes.get("blockedActions", []),
        "oneClickRoutes": routes.get("oneClickRoutes", {}),
    }


if __name__ == "__main__":
    demo_state = {
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
        "businessProfile": {
            "businessName": "Doe Services",
            "entityType": "none",
            "operatingCapacity": "individual",
            "einAvailable": False,
            "separateBusinessBankAccount": False,
        },
        "workProfile": {
            "workerType": "independent_contractor",
            "platformsOrClients": ["Uber", "AV"],
            "setsOwnSchedule": True,
            "providesOwnTools": True,
            "weeklyHoursAverage": 35,
        },
        "incomeProfile": {
            "receivesW2": False,
            "receives1099": True,
            "estimatedAnnualGrossIncome": 85000,
            "estimatedAnnualNetIncome": 65000,
            "hasUnpaidInvoices": True,
        },
        "expenseProfile": {
            "tracksMileage": False,
            "estimatedAnnualBusinessExpenses": 0,
        },
        "complianceProfile": {
            "usesWrittenContracts": False,
            "hasInsurance": False,
            "recordkeepingStrength": "weak",
        },
        "complaintProfile": {
            "hasComplaintOrDispute": True,
            "complaints": [],
        },
        "documentProfile": {
            "w9Ready": False,
            "invoiceReady": False,
            "contractorProfileReady": False,
        },
    }

    result = build_results_summary(demo_state)
    print("overallPositionLabel:", result["overallPositionLabel"])
    print("risk:", result["risk"])
    print("recommendedModules:", result["recommendedModules"])
    print("priorityActions:", result["priorityActions"])
