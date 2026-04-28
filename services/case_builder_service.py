from typing import Any, Dict

from services.complaint_service import build_complaint_packet, get_complaint_summary
from services.evidence_service import get_evidence_summary
from services.timeline_service import build_timeline_packet
from services.legal_intake_service import build_legal_intake_summary


class CaseBuilderServiceError(Exception):
    pass


def build_case_packet(user_id: str, intake_state: Dict[str, Any], complaint_id: str) -> Dict[str, Any]:
    if not user_id:
        raise CaseBuilderServiceError("user_id is required.")
    if not isinstance(intake_state, dict):
        raise CaseBuilderServiceError("intake_state must be a dictionary.")
    if not complaint_id:
        raise CaseBuilderServiceError("complaint_id is required.")

    legal_summary = build_legal_intake_summary(intake_state)
    complaint_packet = build_complaint_packet(user_id, intake_state, complaint_id)
    timeline_packet = build_timeline_packet(intake_state, complaint_id)
    evidence_summary = get_evidence_summary(intake_state)
    complaint_summary = get_complaint_summary(intake_state)

    complaint_item = next(
        (item for item in complaint_summary.get("items", []) if item.get("complaintId") == complaint_id),
        None,
    )

    if complaint_item is None:
        raise CaseBuilderServiceError(f"Complaint not found in summary: {complaint_id}")

    related_evidence_ids = complaint_packet["packet"].get("relatedEvidenceIds", [])
    related_evidence = [
        item for item in evidence_summary.get("items", [])
        if item.get("evidenceId") in related_evidence_ids
    ]

    case_packet = {
        "caseId": f"case-{complaint_id}",
        "complaintId": complaint_id,
        "status": "assembled",
        "intakeStatus": legal_summary.get("intakeStatus"),
        "overallPositionLabel": legal_summary.get("overallPositionLabel"),
        "riskLabel": legal_summary.get("riskLabel"),
        "complaintStrengthLabel": legal_summary.get("complaintStrengthLabel"),
        "summary": {
            "shortTitle": complaint_item.get("shortTitle", ""),
            "targetName": complaint_item.get("targetName", ""),
            "category": complaint_item.get("category", ""),
            "financialLossAmount": complaint_item.get("financialLossAmount", 0),
        },
        "complaintPacket": complaint_packet["packet"],
        "timelinePacket": timeline_packet["timeline"],
        "evidencePacket": related_evidence,
        "recommendedNextActions": legal_summary.get("recommendedNextActions", []),
        "message": "Case packet ready for review",
    }

    return {
        "documentType": "case_packet",
        "status": "generated",
        "valid": True,
        "packet": case_packet,
        "message": "Case packet ready for review",
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
            "platformsOrClients": ["Client A"],
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
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "status": "draft",
                    "category": "payment_issue",
                    "targetName": "Demo Company",
                    "shortTitle": "Unpaid work",
                    "plainLanguageSummary": "Work was completed and payment was not issued.",
                    "whatHappened": "Completed scope and followed up twice.",
                    "financialLossAmount": 1200,
                    "relatedEvidenceIds": ["ev-1"],
                    "timelineEvents": [
                        {
                            "eventId": "t1",
                            "date": "2026-03-28",
                            "event": "Invoice sent",
                            "description": "Invoice emailed to company.",
                            "actor": "user",
                            "source": "email",
                        }
                    ],
                    "curation": {
                        "summaryReady": True,
                        "timelineReady": True,
                        "evidenceMapped": True,
                        "strengthLabel": "moderate",
                        "recommendedRoute": "invoice_demand",
                        "recommendedNextStep": "send_demand",
                    },
                }
            ],
        },
        "evidenceProfile": {
            "hasEvidence": True,
            "evidenceItems": [
                {
                    "evidenceId": "ev-1",
                    "label": "Invoice PDF",
                    "type": "document",
                    "description": "Invoice showing unpaid balance",
                    "source": "user_upload",
                    "fileName": "invoice.pdf",
                    "filePath": "/uploads/invoice.pdf",
                    "date": "2026-03-29",
                    "linkedComplaintIds": ["complaint-1"],
                    "tags": ["invoice", "payment"],
                }
            ],
        },
        "documentProfile": {
            "w9Ready": False,
            "invoiceReady": False,
            "contractorProfileReady": False,
            "documentGenerationHistory": [],
        },
    }

    result = build_case_packet("demo-user", demo_state, "complaint-1")
    print("documentType:", result["documentType"])
    print("status:", result["status"])
    print("caseId:", result["packet"]["caseId"])
    print("message:", result["message"])
