from typing import Any, Dict

from runtime.scoring_executor import compute_scores
from runtime.routing_executor import compute_routes


class UpgradeServiceError(Exception):
    pass


def get_upgrade_options(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise UpgradeServiceError("intake_state must be a dictionary.")

    scores = compute_scores(intake_state)
    routes = compute_routes(intake_state, scores)

    return {
        "recommendedModules": routes.get("recommendedModules", []),
        "upgradePaths": routes.get("upgradePaths", []),
        "priorityActions": routes.get("priorityActions", []),
        "blockedActions": routes.get("blockedActions", []),
        "oneClickRoutes": routes.get("oneClickRoutes", {}),
        "scoreSummary": {
            "classificationScore": scores.get("classificationScore"),
            "savingsOpportunityScore": scores.get("savingsOpportunityScore"),
            "riskScore": scores.get("riskScore"),
            "complaintStrengthScore": scores.get("complaintStrengthScore"),
            "entityReadinessScore": scores.get("entityReadinessScore"),
            "overallPositionLabel": scores.get("overallPositionLabel"),
        },
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

    result = get_upgrade_options(demo_state)
    print("recommendedModules:", result["recommendedModules"])
    print("upgradePaths:", result["upgradePaths"])
    print("blockedActions:", result["blockedActions"])
    print("oneClickRoutes:", result["oneClickRoutes"])
