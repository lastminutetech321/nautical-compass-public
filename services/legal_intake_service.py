from typing import Any, Dict

from runtime.scoring_executor import compute_scores
from services.complaint_service import get_complaint_summary
from services.evidence_service import get_evidence_summary
from services.timeline_service import get_timeline_summary


class LegalIntakeServiceError(Exception):
    pass


def build_legal_intake_summary(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise LegalIntakeServiceError("intake_state must be a dictionary.")

    scores = compute_scores(intake_state)
    complaint_summary = get_complaint_summary(intake_state)
    evidence_summary = get_evidence_summary(intake_state)

    timeline_count = 0
    complaint_packets = []

    for item in complaint_summary.get("items", []):
        complaint_id = item.get("complaintId", "")
        if complaint_id:
            timeline = get_timeline_summary(intake_state, complaint_id)
            timeline_count += timeline.get("eventCount", 0)

        complaint_packets.append(
            {
                "complaintId": item.get("complaintId", ""),
                "category": item.get("category", ""),
                "targetName": item.get("targetName", ""),
                "shortTitle": item.get("shortTitle", ""),
                "financialLossAmount": item.get("financialLossAmount", 0),
                "relatedEvidenceCount": len(item.get("relatedEvidenceIds", [])),
                "timelineEventCount": len(item.get("timelineEvents", [])),
            }
        )

    intake_status = _derive_legal_intake_status(
        complaint_count=complaint_summary.get("complaintCount", 0),
        evidence_count=evidence_summary.get("evidenceCount", 0),
        complaint_strength_score=scores.get("complaintStrengthScore", 0),
    )

    return {
        "intakeStatus": intake_status,
        "complaintCount": complaint_summary.get("complaintCount", 0),
        "evidenceCount": evidence_summary.get("evidenceCount", 0),
        "timelineEventCount": timeline_count,
        "complaintStrengthScore": scores.get("complaintStrengthScore", 0),
        "complaintStrengthLabel": scores.get("complaintStrengthLabel", ""),
        "riskScore": scores.get("riskScore", 0),
        "riskLabel": scores.get("riskLabel", ""),
        "overallPositionLabel": scores.get("overallPositionLabel", ""),
        "complaintPackets": complaint_packets,
        "recommendedNextActions": _recommended_next_actions(
            complaint_count=complaint_summary.get("complaintCount", 0),
            evidence_count=evidence_summary.get("evidenceCount", 0),
            timeline_count=timeline_count,
            complaint_strength_score=scores.get("complaintStrengthScore", 0),
        ),
    }


def _derive_legal_intake_status(
    *,
    complaint_count: int,
    evidence_count: int,
    complaint_strength_score: int,
) -> str:
    if complaint_count == 0:
        return "no_legal_issue_loaded"
    if evidence_count == 0:
        return "complaint_loaded_evidence_needed"
    if complaint_strength_score >= 50:
        return "complaint_ready_for_escalation_review"
    return "complaint_loaded_needs_strengthening"


def _recommended_next_actions(
    *,
    complaint_count: int,
    evidence_count: int,
    timeline_count: int,
    complaint_strength_score: int,
) -> list[str]:
    actions: list[str] = []

    if complaint_count == 0:
        actions.append("add_complaint")
        return actions

    if evidence_count == 0:
        actions.append("upload_evidence")
    if timeline_count == 0:
        actions.append("build_timeline")
    if complaint_strength_score < 50:
        actions.append("strengthen_complaint_summary")
    if evidence_count > 0 and timeline_count > 0:
        actions.append("review_case_packet")

    return actions


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
                    "linkedComplaintIds": ["complaint-1"],
                }
            ],
        },
        "documentProfile": {
            "w9Ready": False,
            "invoiceReady": False,
            "contractorProfileReady": False,
        },
    }

    result = build_legal_intake_summary(demo_state)
    print("intakeStatus:", result["intakeStatus"])
    print("complaintCount:", result["complaintCount"])
    print("evidenceCount:", result["evidenceCount"])
    print("timelineEventCount:", result["timelineEventCount"])
    print("recommendedNextActions:", result["recommendedNextActions"])
