from typing import Any, Dict, List

from services.standing_analysis_service import analyze_standing
from services.capacity_analysis_service import analyze_capacity
from services.jurisdiction_service import analyze_jurisdiction
from services.rights_violation_service import analyze_rights_violations
from services.regulatory_routing_service import analyze_regulatory_routes


class LegalResultsServiceError(Exception):
    pass


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_legal_results(intake_state: Dict[str, Any], complaint_id: str | None = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise LegalResultsServiceError("intake_state must be a dictionary.")

    standing = analyze_standing(intake_state, complaint_id)
    capacity = analyze_capacity(intake_state, complaint_id)
    jurisdiction = analyze_jurisdiction(intake_state, complaint_id)
    rights = analyze_rights_violations(intake_state, complaint_id)
    regulatory = analyze_regulatory_routes(intake_state, complaint_id)

    complaint_id_value = standing.get("complaintId", complaint_id or "")

    standing_score = int(standing.get("overallStandingScore", 0))
    rights_severity = int(rights.get("rightsAnalysis", {}).get("severityScore", 0))
    jurisdiction_track = jurisdiction.get("jurisdictionAnalysis", {}).get("primaryTrack", "")
    capacity_target_type = capacity.get("capacityAnalysis", {}).get("targetType", "")
    regulatory_strength = regulatory.get("regulatoryRouting", {}).get("routingStrength", "")

    overall_label = "general_review"

    if standing_score >= 60 and rights_severity >= 60 and jurisdiction_track == "public_law":
        overall_label = "public_law_escalation_candidate"
    elif standing_score >= 60 and jurisdiction_track == "private_dispute":
        overall_label = "private_claim_escalation_candidate"
    elif regulatory_strength in {"multi_route", "moderate_route"}:
        overall_label = "regulatory_review_candidate"
    elif standing_score >= 30:
        overall_label = "claim_needs_strengthening"
    else:
        overall_label = "fact_pattern_needs_development"

    next_actions = _dedupe(
        standing.get("recommendedNextActions", [])
        + capacity.get("recommendedNextActions", [])
        + jurisdiction.get("recommendedNextActions", [])
        + rights.get("recommendedNextActions", [])
        + regulatory.get("recommendedNextActions", [])
    )

    rights_flags = rights.get("rightsAnalysis", {}).get("rightsFlags", [])
    regulatory_routes = regulatory.get("regulatoryRouting", {}).get("routes", [])

    return {
        "complaintId": complaint_id_value,
        "overallLegalPostureLabel": overall_label,
        "targetType": capacity_target_type,
        "standingSummary": {
            "score": standing_score,
            "label": standing.get("overallStandingLabel", ""),
            "articleIIIStanding": standing.get("articleIIIStanding", {}),
        },
        "capacitySummary": {
            "targetType": capacity_target_type,
            "capacityOptions": capacity.get("capacityAnalysis", {}).get("capacityOptions", []),
            "reliefTrack": capacity.get("capacityAnalysis", {}).get("reliefTrack", ""),
        },
        "jurisdictionSummary": {
            "primaryTrack": jurisdiction_track,
            "recommendations": jurisdiction.get("jurisdictionAnalysis", {}).get("recommendations", []),
            "venueNotes": jurisdiction.get("jurisdictionAnalysis", {}).get("venueNotes", []),
        },
        "rightsSummary": {
            "severityScore": rights_severity,
            "severityLabel": rights.get("rightsAnalysis", {}).get("severityLabel", ""),
            "rightsFlags": rights_flags,
        },
        "regulatorySummary": {
            "routingStrength": regulatory_strength,
            "routes": regulatory_routes,
        },
        "recommendedNextActions": next_actions,
        "notes": [
            standing.get("note", ""),
            capacity.get("note", ""),
            jurisdiction.get("note", ""),
            rights.get("note", ""),
            regulatory.get("note", ""),
        ],
    }


if __name__ == "__main__":
    demo_state = {
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
    }

    result = build_legal_results(demo_state, "complaint-1")
    print("complaintId:", result["complaintId"])
    print("overallLegalPostureLabel:", result["overallLegalPostureLabel"])
    print("standingLabel:", result["standingSummary"]["label"])
    print("rightsFlags:", result["rightsSummary"]["rightsFlags"])
    print("recommendedNextActions:", result["recommendedNextActions"])
