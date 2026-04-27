from typing import Any, Dict, List

from engines.guardian_engine import evaluate_guardian_state
from services.evidence_service import get_evidence_summary
from services.complaint_service import get_complaint_summary


class GuardianEvidenceIntakeServiceError(Exception):
    pass


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_guardian_evidence_intake(intake_state: Dict[str, Any], scores: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise GuardianEvidenceIntakeServiceError("intake_state must be a dictionary.")

    guardian = evaluate_guardian_state(intake_state, scores or {})
    evidence = get_evidence_summary(intake_state)
    complaints = get_complaint_summary(intake_state)

    evidence_gaps: List[str] = []
    complaint_items = complaints.get("items", [])

    for item in complaint_items:
        complaint_id = item.get("complaintId", "")
        related_evidence = item.get("relatedEvidenceIds", []) or []
        if complaint_id and not related_evidence:
            evidence_gaps.append(f"{complaint_id}: no linked evidence")

    if complaints.get("hasComplaint") and evidence.get("evidenceCount", 0) == 0:
        evidence_gaps.append("no evidence uploaded for active complaint set")

    intake_readiness = "ready"
    if guardian.get("guardianStatus") == "critical":
        intake_readiness = "urgent"
    elif evidence_gaps:
        intake_readiness = "needs_evidence"

    recommended_next_actions = _dedupe(
        guardian.get("protectiveActions", [])
        + (["upload_evidence", "link_evidence_to_complaint"] if evidence_gaps else [])
    )

    return {
        "guardianStatus": guardian.get("guardianStatus"),
        "guardianScore": guardian.get("guardianScore"),
        "alerts": guardian.get("alerts", []),
        "protectiveActions": guardian.get("protectiveActions", []),
        "evidenceCount": evidence.get("evidenceCount", 0),
        "complaintCount": complaints.get("complaintCount", 0),
        "evidenceGaps": evidence_gaps,
        "intakeReadiness": intake_readiness,
        "recommendedNextActions": recommended_next_actions,
        "message": "Guardian evidence intake summary ready",
    }


if __name__ == "__main__":
    demo_state = {
        "businessProfile": {
            "entityType": "none",
            "separateBusinessBankAccount": False,
        },
        "complianceProfile": {
            "hasInsurance": False,
            "usesWrittenContracts": False,
            "recordkeepingStrength": "weak",
        },
        "incomeProfile": {
            "hasUnpaidInvoices": True,
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
                    "plainLanguageSummary": "Completed work but payment was not made.",
                    "relatedEvidenceIds": [],
                    "timelineEvents": [],
                }
            ],
        },
        "evidenceProfile": {
            "hasEvidence": False,
            "evidenceItems": [],
        },
    }

    demo_scores = {
        "riskScore": 82,
        "complaintStrengthScore": 35,
        "documentReadinessScore": 20,
    }

    result = build_guardian_evidence_intake(demo_state, demo_scores)
    print("guardianStatus:", result["guardianStatus"])
    print("evidenceCount:", result["evidenceCount"])
    print("evidenceGaps:", result["evidenceGaps"])
    print("intakeReadiness:", result["intakeReadiness"])
    print("recommendedNextActions:", result["recommendedNextActions"])
