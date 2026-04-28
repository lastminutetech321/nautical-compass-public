from typing import Any, Dict

from runtime.execution_orchestrator import handle_generate_w9


class DocumentServiceError(Exception):
    pass


def generate_w9(
    user_id: str,
    intake_state: Dict[str, Any],
) -> Dict[str, Any]:
    if not user_id:
        raise DocumentServiceError("user_id is required.")
    if not isinstance(intake_state, dict):
        raise DocumentServiceError("intake_state must be a dictionary.")

    return handle_generate_w9(
        user_id=user_id,
        intake_state=intake_state,
    )


if __name__ == "__main__":
    demo_user = "demo-user"

    demo_state = {
        "intakeId": "",
        "intakeVersion": "v1",
        "createdAt": "",
        "updatedAt": "",
        "userId": demo_user,
        "mode": "general",
        "status": "complete",
        "completionPercent": 100,
        "identityProfile": {
            "fullLegalName": "Jane Doe",
            "firstName": "Jane",
            "lastName": "Doe",
            "dateOfBirth": "",
            "phone": "555-123-4567",
            "email": "jane@example.com",
            "residentialAddress": {
                "street1": "123 Harbor Way",
                "city": "Baltimore",
                "state": "MD",
                "postalCode": "21201",
                "country": "US"
            }
        },
        "businessProfile": {
            "operatingCapacity": "individual",
            "entityType": "none",
            "businessName": "Doe Services",
            "einAvailable": False,
            "separateBusinessBankAccount": False
        },
        "workProfile": {
            "workerType": "independent_contractor",
            "platformsOrClients": [],
            "setsOwnSchedule": True,
            "providesOwnTools": True,
            "weeklyHoursAverage": 35
        },
        "incomeProfile": {
            "receivesW2": False,
            "receives1099": True,
            "estimatedAnnualGrossIncome": 85000,
            "estimatedAnnualNetIncome": 65000,
            "hasUnpaidInvoices": True
        },
        "expenseProfile": {
            "usesVehicleForWork": False,
            "tracksMileage": False,
            "estimatedAnnualBusinessExpenses": 0
        },
        "complianceProfile": {
            "hasSeparateFinances": False,
            "usesWrittenContracts": False,
            "hasInsurance": False,
            "recordkeepingStrength": "weak"
        },
        "complaintProfile": {
            "hasComplaintOrDispute": False,
            "complaints": []
        },
        "documentProfile": {
            "w9Ready": False,
            "invoiceReady": False,
            "contractorProfileReady": False
        },
        "evidenceProfile": {
            "hasEvidence": False,
            "evidenceItems": []
        },
        "history": []
    }

    result = generate_w9(demo_user, demo_state)

    print("documentType:", result["documentType"])
    print("valid:", result["reviewState"]["valid"])
    print("status:", result["reviewState"]["status"])
    print("history_count:", len(result["intakeState"]["documentProfile"]["documentGenerationHistory"]))
