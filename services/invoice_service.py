from typing import Any, Dict

from runtime.prefill_mapper import map_document_fields
from runtime.document_history_logger import append_document_record, set_document_ready_flag


class InvoiceServiceError(Exception):
    pass


def generate_invoice_payload(user_id: str, intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not user_id:
        raise InvoiceServiceError("user_id is required.")
    if not isinstance(intake_state, dict):
        raise InvoiceServiceError("intake_state must be a dictionary.")

    mapped = map_document_fields("invoice", intake_state)

    if not mapped.get("valid", False):
        return {
            "documentType": "invoice",
            "status": "blocked",
            "valid": False,
            "missingFields": mapped.get("missingFields", []),
            "payload": {},
            "message": "Missing required intake fields",
            "intakeState": intake_state,
        }

    fields = mapped.get("mappedFields", {})

    payload = {
        "fromName": fields.get("fromName", "") or "",
        "fromContact": fields.get("fromContact", "") or "",
        "fromPhone": fields.get("fromPhone", "") or "",
        "serviceProviderName": fields.get("serviceProviderName", "") or "",
        "workerType": fields.get("workerType", "") or "",
        "platformsOrClients": fields.get("platformsOrClients", []) or [],
        "estimatedAnnualGrossIncome": fields.get("estimatedAnnualGrossIncome", 0) or 0,
        "invoiceNumber": "",
        "invoiceDate": "",
        "clientName": "",
        "serviceDescription": "",
        "amountDue": 0,
        "status": "draft",
    }

    updated_state = append_document_record(
        user_id,
        intake_state,
        {
            "documentId": "doc-invoice-runtime",
            "documentType": "invoice",
            "title": "Invoice Draft",
            "fileName": "invoice-draft.json",
            "filePath": "/generated/invoice-draft.json",
            "status": "generated",
            "notes": "invoice payload generated",
        },
    )
    updated_state = set_document_ready_flag(updated_state, "invoice")

    return {
        "documentType": "invoice",
        "status": "prefilled",
        "valid": True,
        "missingFields": [],
        "payload": payload,
        "message": "Invoice payload ready for review",
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
        },
        "incomeProfile": {
            "estimatedAnnualGrossIncome": 85000,
        },
        "documentProfile": {
            "invoiceReady": True,
        },
    }

    result = generate_invoice_payload("demo-user", demo_state)
    print("documentType:", result["documentType"])
    print("valid:", result["valid"])
    print("status:", result["status"])
    print("message:", result["message"])
