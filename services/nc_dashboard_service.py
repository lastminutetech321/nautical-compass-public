from typing import Any, Dict

from services.legal_results_service import build_legal_results
from services.guardian_evidence_intake_service import build_guardian_evidence_intake
from services.results_service import build_results_summary
from runtime.helm_state_adapter import build_helm_state
from runtime.scoring_executor import compute_scores
from runtime.routing_executor import compute_routes


class NCDashboardServiceError(Exception):
    pass


def build_nc_dashboard(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise NCDashboardServiceError("intake_state must be a dictionary.")

    scores = compute_scores(intake_state)
    routes = compute_routes(intake_state, scores)
    history = intake_state.get("documentProfile", {}).get("documentGenerationHistory", []) or []

    helm = build_helm_state(intake_state, scores, routes, history)
    results = build_results_summary(intake_state)
    legal = build_legal_results(intake_state, complaint_id) if intake_state.get("complaintProfile", {}).get("complaints") else {
        "complaintId": "",
        "overallLegalPostureLabel": "no_legal_issue_loaded",
        "standingSummary": {},
        "capacitySummary": {},
        "jurisdictionSummary": {},
        "rightsSummary": {},
        "regulatorySummary": {},
        "recommendedNextActions": [],
        "notes": [],
    }
    guardian = build_guardian_evidence_intake(intake_state, scores)

    return {
        "dashboard": {
            "helm": helm,
            "results": results,
            "legal": legal,
            "guardian": guardian,
        },
        "summary": {
            "overallPositionLabel": results.get("overallPositionLabel"),
            "overallLegalPostureLabel": legal.get("overallLegalPostureLabel"),
            "guardianStatus": guardian.get("guardianStatus"),
            "recommendedModules": results.get("recommendedModules", []),
            "recommendedNextActions": _dedupe(
                results.get("priorityActions", [])
                + legal.get("recommendedNextActions", [])
                + guardian.get("recommendedNextActions", [])
            ),
        },
        "message": "NC dashboard payload ready",
    }


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


if __name__ == "__main__":
    demo_state = {
        "completionPercent": 85,
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
                    "targetType": "government",
                    "targetName": "City Police Department",
                    "targetDepartment": "Internal Affairs",
                    "targetPerson": "Officer Smith",
                    "category": "civil_rights",
                    "shortTitle": "Unlawful stop and retaliation",
                    "plainLanguageSummary": "I was stopped, detained, and retaliated against after making a complaint.",
                    "whatHappened": "Officer stopped me, detained me, searched my property, and threatened me after I protested.",
                    "whatWasSaid": "They told me to stop complaining.",
                    "desiredOutcome": "Injunction and damages",
                    "financialLossAmount": 2500,
                    "workLossAmount": 0,
                    "timeLostHours": 4,
                    "injuryClaimed": True,
                    "propertyDamageClaimed": False,
                    "creditImpactClaimed": False,
                    "emotionalStressClaimed": False,
                    "priorComplaintMade": True,
                    "relatedEvidenceIds": ["ev-1"],
                    "timelineEvents": [
                        {
                            "eventId": "t1",
                            "date": "2026-03-28",
                            "event": "Stop occurred",
                            "description": "Initial stop and detention.",
                            "actor": "officer",
                            "source": "personal_knowledge",
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
                    "label": "Phone video",
                    "type": "video",
                    "linkedComplaintIds": ["complaint-1"],
                }
            ],
        },
        "documentProfile": {
            "w9Ready": True,
            "invoiceReady": False,
            "contractorProfileReady": False,
            "documentGenerationHistory": [
                {"documentType": "w9", "status": "generated"}
            ],
        },
    }

    result = build_nc_dashboard(demo_state, "complaint-1")
    print("message:", result["message"])
    print("overallPositionLabel:", result["summary"]["overallPositionLabel"])
    print("overallLegalPostureLabel:", result["summary"]["overallLegalPostureLabel"])
    print("guardianStatus:", result["summary"]["guardianStatus"])
    print("recommendedNextActions:", result["summary"]["recommendedNextActions"])
