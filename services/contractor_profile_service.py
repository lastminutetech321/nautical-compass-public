from typing import Any, Dict

from runtime.prefill_mapper import map_document_fields
from runtime.document_history_logger import append_document_record, set_document_ready_flag


class ContractorProfileServiceError(Exception):
    pass


def generate_contractor_profile(user_id: str, intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not user_id:
        raise ContractorProfileServiceError("user_id is required.")
    if not isinstance(intake_state, dict):
        raise ContractorProfileServiceError("intake_state must be a dictionary.")

    mapped = map_document_fields("contractorProfile", intake_state)

    if not mapped.get("valid", False):
        return {
            "documentType": "contractor_profile",
            "status": "blocked",
            "valid": False,
            "missingFields": mapped.get("missingFields", []),
            "payload": {},
            "message": "Missing required intake fields",
            "intakeState": intake_state,
        }

    fields = mapped.get("mappedFields", {})

    payload = {
        "fullName": fields.get("fullName", "") or "",
        "email": fields.get("email", "") or "",
        "phone": fields.get("phone", "") or "",
        "businessName": fields.get("businessName", "") or "",
        "workerType": fields.get("workerType", "") or "",
        "platformsOrClients": fields.get("platformsOrClients", []) or [],
        "setsOwnSchedule": fields.get("setsOwnSchedule", False),
        "providesOwnTools": fields.get("providesOwnTools", False),
        "weeklyHoursAverage": fields.get("weeklyHoursAverage", 0) or 0,
        "estimatedAnnualGrossIncome": fields.get("estimatedAnnualGrossIncome", 0) or 0,
        "recordkeepingStrength": fields.get("recordkeepingStrength", "") or "",
        "profileStatus": "draft",
    }

    updated_state = append_document_record(
        user_id,
        intake_state,
        {
            "documentId": "doc-contractor-profile-runtime",
            "documentType": "contractor_profile",
            "title": "Contractor Profile Draft",
            "fileName": "contractor-profile-draft.json",
            "filePath": "/generated/contractor-profile-draft.json",
            "status": "generated",
            "notes": "contractor profile payload generated",
        },
    )
    updated_state = set_document_ready_flag(updated_state, "contractor_profile")

    return {
        "documentType": "contractor_profile",
        "status": "prefilled",
        "valid": True,
        "missingFields": [],
        "payload": payload,
        "message": "Contractor profile payload ready for review",
        "intakeState": updated_state,
    }


if __name__ == "__main__":
    demo_state = {
        "identityProfile": {
            "fullLegalName": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-123-4567",
        },
        "businessProfile": {
            "businessName": "Doe Services",
        },
        "workProfile": {
            "workerType": "independent_contractor",
            "platformsOrClients": ["Uber", "AV"],
            "setsOwnSchedule": True,
            "providesOwnTools": True,
            "weeklyHoursAverage": 35,
        },
        "incomeProfile": {
            "estimatedAnnualGrossIncome": 85000,
        },
        "complianceProfile": {
            "recordkeepingStrength": "weak",
        },
    }

    result = generate_contractor_profile("demo-user", demo_state)
    print("documentType:", result["documentType"])
    print("valid:", result["valid"])
    print("status:", result["status"])
    print("message:", result["message"])
