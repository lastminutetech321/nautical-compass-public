"""
Legal results aggregator — combines standing, capacity, rights, jurisdiction analysis
into a unified posture assessment.
"""
from typing import Any, Dict, List, Optional

from services.standing_analysis_service import analyze_standing
from services.capacity_analysis_service import analyze_capacity
from services.jurisdiction_service import analyze_jurisdiction
from services.rights_violation_service import analyze_rights_violations
from services.regulatory_routing_service import analyze_regulatory_routes


class LegalResultsServiceError(Exception):
    pass


def _dedupe(items: List[str]) -> List[str]:
    seen: set = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _score_overall_strength(
    standing: Dict[str, Any],
    rights: Dict[str, Any],
    jurisdiction: Dict[str, Any],
) -> str:
    """
    Strong: standing established + at least one claim detected + federal jurisdiction confirmed.
    Moderate: standing established + federal jurisdiction, OR standing + claims without federal jurisdiction.
    Weak: standing not established, or no claims detected.
    """
    standing_ok = standing.get("standing", False)
    has_claims = bool(rights.get("claims")) or bool(rights.get("constitutional_violations"))
    federal_ok = jurisdiction.get("federal_question", False) or jurisdiction.get("civil_rights_jurisdiction", False)
    severity = rights.get("severity_score", 0)

    if standing_ok and has_claims and federal_ok and severity >= 30:
        return "strong"
    if standing_ok and (has_claims or federal_ok):
        return "moderate"
    return "weak"


def _collect_next_actions(
    standing: Dict[str, Any],
    capacity: Dict[str, Any],
    rights: Dict[str, Any],
    jurisdiction: Dict[str, Any],
    regulatory: Dict[str, Any],
) -> List[str]:
    actions: List[str] = []

    if not standing.get("injury_in_fact", {}).get("met"):
        actions.append("strengthen_injury_allegations — add financial loss, injury, or property damage facts")
    if not standing.get("causation", {}).get("met"):
        actions.append("identify_defendant_and_conduct — name the actor and describe their specific actions")
    if not standing.get("redressability", {}).get("met"):
        actions.append("state_desired_relief — specify damages, injunction, or corrective action sought")

    if capacity.get("sovereign_immunity_applies"):
        actions.append("name_individual_officer_for_damages — official-capacity claims against state are damages-barred")
    if capacity.get("ex_parte_young_available"):
        actions.append("plead_ex_parte_young_injunction — injunctive relief against state officer available")

    if not rights.get("claims"):
        actions.append("identify_specific_claim_basis — specify constitutional amendment or federal statute violated")
    if rights.get("municipal_liability") and "policy" not in " ".join(
        [c.get("basis", "") for c in rights.get("claims", [])]
    ):
        actions.append("allege_municipal_policy_or_custom — Monell requires more than respondeat superior")

    if jurisdiction.get("recommended_court") == "federal_district":
        actions.append("file_in_federal_district_court — §1331/§1343 jurisdiction confirmed")
    else:
        actions.append("evaluate_state_court_forum — no federal question detected")

    for route in regulatory.get("regulatoryRouting", {}).get("routes", []):
        if route.get("code") == "consumer_credit_regulator":
            actions.append("prepare_consumer_credit_packet — regulatory complaint path available")
        if route.get("code") == "debt_collection_regulator":
            actions.append("prepare_fdcpa_complaint_packet — debt collection regulatory path available")

    return _dedupe(actions)


def build_legal_results(intake_state: Dict[str, Any], complaint_id: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise LegalResultsServiceError("intake_state must be a dictionary.")

    standing = analyze_standing(intake_state, complaint_id)
    capacity = analyze_capacity(intake_state, complaint_id)
    jurisdiction = analyze_jurisdiction(intake_state, complaint_id)
    rights = analyze_rights_violations(intake_state, complaint_id)
    regulatory = analyze_regulatory_routes(intake_state, complaint_id)

    complaint_id_value = standing.get("complaintId", complaint_id or "")
    overall_strength = _score_overall_strength(standing, rights, jurisdiction)
    next_actions = _collect_next_actions(standing, capacity, rights, jurisdiction, regulatory)

    all_case_law = _dedupe(
        standing.get("case_law", [])
        + capacity.get("case_law", [])
        + rights.get("case_law", [])
        + jurisdiction.get("case_law", [])
    )

    return {
        "complaintId": complaint_id_value,
        "overall_strength": overall_strength,
        "standing": {
            "established": standing.get("standing", False),
            "label": standing.get("standing_label", ""),
            "injury_in_fact": standing.get("injury_in_fact", {}),
            "causation": standing.get("causation", {}),
            "redressability": standing.get("redressability", {}),
            "case_law": standing.get("case_law", []),
        },
        "capacity": {
            "target_type": capacity.get("target_type", ""),
            "capacity_label": capacity.get("capacity_label", ""),
            "recommended_defendants": capacity.get("recommended_defendants", []),
            "capacity_split": capacity.get("capacity_split", {}),
            "immunity_risk": capacity.get("immunity_risk", ""),
            "sovereign_immunity_applies": capacity.get("sovereign_immunity_applies", False),
            "ex_parte_young_available": capacity.get("ex_parte_young_available", False),
            "case_law": capacity.get("case_law", []),
        },
        "rights": {
            "claims": rights.get("claims", []),
            "constitutional_violations": rights.get("constitutional_violations", []),
            "municipal_liability": rights.get("municipal_liability", False),
            "municipal_liability_analysis": rights.get("municipal_liability_analysis", ""),
            "severity_score": rights.get("severity_score", 0),
            "severity_label": rights.get("severity_label", ""),
            "case_law": rights.get("case_law", []),
        },
        "jurisdiction": {
            "federal_question": jurisdiction.get("federal_question", False),
            "civil_rights_jurisdiction": jurisdiction.get("civil_rights_jurisdiction", False),
            "recommended_court": jurisdiction.get("recommended_court", ""),
            "venue_notes": jurisdiction.get("venue_notes", ""),
            "supplemental_jurisdiction": jurisdiction.get("supplemental_jurisdiction", {}),
            "case_law": jurisdiction.get("case_law", []),
        },
        "all_case_law": all_case_law,
        "recommended_next_actions": next_actions,
        "notes": [
            standing.get("note", ""),
            capacity.get("note", ""),
            rights.get("note", ""),
            jurisdiction.get("note", ""),
        ],
    }
