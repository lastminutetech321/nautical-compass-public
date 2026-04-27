from typing import Any, Dict

from runtime.execution_orchestrator import (
    handle_field_update,
    handle_intake_completion,
    handle_section_save,
)


class IntakeServiceError(Exception):
    pass


def save_field(
    user_id: str,
    field_path: str,
    value: Any,
    intake_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not user_id:
        raise IntakeServiceError("user_id is required.")
    if not field_path:
        raise IntakeServiceError("field_path is required.")

    return handle_field_update(
        user_id=user_id,
        field_path=field_path,
        value=value,
        intake_state=intake_state,
    )


def save_section(
    user_id: str,
    section_id: str,
    payload: Dict[str, Any],
    intake_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not user_id:
        raise IntakeServiceError("user_id is required.")
    if not section_id:
        raise IntakeServiceError("section_id is required.")
    if not isinstance(payload, dict):
        raise IntakeServiceError("payload must be a dictionary.")

    return handle_section_save(
        user_id=user_id,
        section_id=section_id,
        payload=payload,
        intake_state=intake_state,
    )


def complete_intake(
    user_id: str,
    intake_state: Dict[str, Any],
) -> Dict[str, Any]:
    if not user_id:
        raise IntakeServiceError("user_id is required.")
    if not isinstance(intake_state, dict):
        raise IntakeServiceError("intake_state must be a dictionary.")

    return handle_intake_completion(
        user_id=user_id,
        intake_state=intake_state,
    )


if __name__ == "__main__":
    demo_user = "demo-user"

    payload = {
        "identityProfile.fullLegalName": "Jane Doe",
        "identityProfile.firstName": "Jane",
        "identityProfile.lastName": "Doe",
        "identityProfile.email": "jane@example.com",
        "identityProfile.phone": "555-123-4567",
        "identityProfile.residentialAddress.street1": "123 Harbor Way",
        "identityProfile.residentialAddress.city": "Baltimore",
        "identityProfile.residentialAddress.state": "MD",
        "identityProfile.residentialAddress.postalCode": "21201",
        "workProfile.workerType": "independent_contractor",
        "incomeProfile.estimatedAnnualGrossIncome": 85000,
        "businessProfile.businessName": "Doe Services",
        "businessProfile.entityType": "none",
        "businessProfile.einAvailable": False,
        "incomeProfile.receives1099": True,
        "workProfile.setsOwnSchedule": True,
        "workProfile.providesOwnTools": True,
        "incomeProfile.hasUnpaidInvoices": True,
        "complaintProfile.hasComplaintOrDispute": True,
    }

    section_result = save_section(demo_user, "identity", payload)
    completed = complete_intake(demo_user, section_result["intakeState"])

    print("section_valid:", section_result["validation"]["valid"])
    print("results_generateW9Enabled:", completed["resultsScreen"]["generateW9Enabled"])
    print("recommendedModules:", completed["routes"]["recommendedModules"])
