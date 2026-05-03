"""
Capacity analysis applying:
  Kentucky v. Graham, 473 U.S. 159 (1985) — official capacity = entity; individual = personal liability
  Ex parte Young, 209 U.S. 123 (1908) — injunctive relief against state officers permitted despite 11th Amendment
  Will v. Michigan Dept. of State Police, 491 U.S. 58 (1989) — state not a "person" under §1983
  Hafer v. Melo, 502 U.S. 21 (1991) — state officers personally liable under §1983 in individual capacity
  Eleventh Amendment — sovereign immunity bars federal court suits against states for damages
"""
from typing import Any, Dict, List, Optional

CASE_LAW = [
    "Kentucky v. Graham, 473 U.S. 159 (1985)",
    "Ex parte Young, 209 U.S. 123 (1908)",
    "Will v. Michigan Dept. of State Police, 491 U.S. 58 (1989)",
    "Hafer v. Melo, 502 U.S. 21 (1991)",
    "U.S. Const. amend. XI (Eleventh Amendment — sovereign immunity)",
]


class CapacityAnalysisServiceError(Exception):
    pass


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _safe_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_target_type(complaint: Dict[str, Any]) -> str:
    target_type = (complaint.get("targetType", "") or "").strip().lower()
    if target_type in {"government", "private"}:
        return target_type

    target_name = (complaint.get("targetName", "") or "").strip().lower()
    government_terms = [
        "police", "sheriff", "department", "agency", "city", "county", "state",
        "officer", "judge", "court", "board", "commission", "school district",
        "municipality", "bureau", "authority", "district",
    ]
    return "government" if any(t in target_name for t in government_terms) else "private"


def _is_state_level(complaint: Dict[str, Any]) -> bool:
    target_name = (complaint.get("targetName", "") or "").lower()
    state_terms = ["state", "department of", "state police", "state board", "state agency"]
    return any(t in target_name for t in state_terms)


def _analyze_government_capacity(complaint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Kentucky v. Graham (1985): Official-capacity suit is a suit against the government entity itself.
    Individual-capacity suit targets the officer personally and requires showing the officer's own conduct.
    Will (1989): The State and state officials in their official capacity are not 'persons' under §1983
    for purposes of damages — but municipalities and local governments are (Monell).
    Ex parte Young (1908): A state officer can be sued in official capacity for prospective injunctive
    relief to end an ongoing constitutional violation, despite the Eleventh Amendment.
    Hafer (1991): State officers sued in individual capacity ARE 'persons' under §1983 and may be
    held personally liable for damages.
    """
    target_name = complaint.get("targetName", "") or ""
    target_person = complaint.get("targetPerson", "") or ""
    target_department = complaint.get("targetDepartment", "") or ""
    desired_outcome = (complaint.get("desiredOutcome", "") or "").lower()
    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    injury_claimed = _safe_bool(complaint.get("injuryClaimed"))
    property_damage = _safe_bool(complaint.get("propertyDamageClaimed"))

    is_state = _is_state_level(complaint)
    seeks_injunction = any(t in desired_outcome for t in ["stop", "injunction", "cease", "enjoin", "prevent", "policy"])
    seeks_damages = financial_loss > 0 or injury_claimed or property_damage or any(
        t in desired_outcome for t in ["damages", "compensation", "payment", "reimburse"]
    )

    individual_defendants: List[str] = []
    official_defendants: List[str] = []
    recommended: List[str] = []
    immunity_notes: List[str] = []

    if target_person:
        individual_defendants.append(target_person)
        recommended.append(f"{target_person} (individual capacity)")
        if seeks_damages:
            immunity_notes.append(
                f"{target_person} may raise qualified immunity — plaintiff must show violation of clearly established law. "
                "See Harlow v. Fitzgerald, 457 U.S. 800 (1982)."
            )

    if target_name or target_department:
        entity = target_department or target_name
        official_defendants.append(entity)
        if seeks_injunction and is_state:
            recommended.append(
                f"{entity} official (official capacity, injunctive relief only) — "
                "Ex parte Young exception applies to prospective injunctive relief against state officers"
            )
        elif seeks_injunction:
            recommended.append(f"{entity} (official capacity, injunctive relief)")
        if seeks_damages and not is_state:
            recommended.append(
                f"{entity} (official capacity, damages) — viable if {entity} is a municipality or local government; "
                "Will v. Michigan bars damages against the State itself in federal court"
            )

    sovereign_immunity_applies = is_state and seeks_damages and not target_person
    ex_parte_young_available = is_state and seeks_injunction

    if sovereign_immunity_applies:
        immunity_notes.append(
            "Eleventh Amendment sovereign immunity bars damages claims against the State in federal court. "
            "Will v. Michigan Dept. of State Police, 491 U.S. 58 (1989). "
            "To recover damages, name the individual officer in their individual capacity."
        )
    if ex_parte_young_available:
        immunity_notes.append(
            "Ex parte Young exception available: injunctive relief against a state officer in official capacity "
            "to stop an ongoing constitutional violation is not barred by the Eleventh Amendment. "
            "Ex parte Young, 209 U.S. 123 (1908)."
        )
    if not individual_defendants and not official_defendants:
        immunity_notes.append("No specific defendant identified. Name individuals and entities separately.")

    return {
        "individual_defendants": individual_defendants,
        "official_defendants": official_defendants,
        "recommended_defendants": recommended,
        "sovereign_immunity_applies": sovereign_immunity_applies,
        "ex_parte_young_available": ex_parte_young_available,
        "seeks_damages": seeks_damages,
        "seeks_injunction": seeks_injunction,
        "immunity_notes": immunity_notes,
    }


def _analyze_private_capacity(complaint: Dict[str, Any]) -> Dict[str, Any]:
    target_name = complaint.get("targetName", "") or ""
    target_person = complaint.get("targetPerson", "") or ""

    individual_defendants: List[str] = []
    official_defendants: List[str] = []
    recommended: List[str] = []

    if target_person:
        individual_defendants.append(target_person)
        recommended.append(f"{target_person} (individual — personal liability)")
    if target_name:
        # Private entities are NOT official-capacity defendants; keep official_defendants empty
        # so downstream complaint generation uses direct corporate liability framing instead.
        recommended.append(f"{target_name} (entity — direct corporate/business liability)")

    return {
        "individual_defendants": individual_defendants,
        "official_defendants": official_defendants,
        "recommended_defendants": recommended,
        "sovereign_immunity_applies": False,
        "ex_parte_young_available": False,
        "seeks_damages": True,
        "seeks_injunction": False,
        "immunity_notes": [
            "Private actor — Eleventh Amendment sovereign immunity does not apply. "
            "Standard tortious or contractual liability rules govern."
        ],
    }


def analyze_capacity(intake_state: Dict[str, Any], complaint_id: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise CapacityAnalysisServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise CapacityAnalysisServiceError("No complaints found in intake_state.")

    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise CapacityAnalysisServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    target_type = _normalize_target_type(complaint)

    if target_type == "government":
        analysis = _analyze_government_capacity(complaint)
        immunity_risk = (
            "HIGH — State-level government target. Eleventh Amendment sovereign immunity applies to damages. "
            "Kentucky v. Graham (1985): name defendants in both individual and official capacity. "
            "Damages require individual-capacity claims against specific officers."
            if _is_state_level(complaint)
            else
            "MODERATE — Local government target (municipality/county). Sovereign immunity limited. "
            "Municipal liability available under Monell v. Dept. of Social Services (1978) if policy/custom shown."
        )
    else:
        analysis = _analyze_private_capacity(complaint)
        immunity_risk = "LOW — Private actor. No sovereign immunity. Standard liability rules apply."

    capacity_label = (
        "government_actor_split_capacity_required"
        if target_type == "government"
        else "private_actor_direct_liability"
    )

    if target_type == "government":
        analysis_text = (
            f"GOVERNMENT TARGET — Kentucky v. Graham (1985) requires naming defendants in both capacities. "
            f"Official-capacity suit = suit against the entity ({complaint.get('targetName', 'entity')} itself). "
            f"Individual-capacity suit = personal liability against the named officer. "
            f"{analysis['immunity_notes'][0] if analysis['immunity_notes'] else ''}"
        )
    else:
        analysis_text = (
            "PRIVATE TARGET — Standard individual and entity liability. No Eleventh Amendment issues. "
            f"Recommended defendants: {', '.join(analysis['recommended_defendants']) or 'not yet identified'}."
        )

    return {
        "complaintId": complaint.get("complaintId", ""),
        "targetName": complaint.get("targetName", ""),
        "targetPerson": complaint.get("targetPerson", ""),
        "target_type": target_type,
        "capacity_label": capacity_label,
        "recommended_defendants": analysis["recommended_defendants"],
        "capacity_split": {
            "individual": analysis["individual_defendants"],
            "official": analysis["official_defendants"],
        },
        "immunity_risk": immunity_risk,
        "sovereign_immunity_applies": analysis["sovereign_immunity_applies"],
        "ex_parte_young_available": analysis["ex_parte_young_available"],
        "immunity_notes": analysis["immunity_notes"],
        "analysis": analysis_text,
        "case_law": CASE_LAW,
        "note": (
            "Intake-level capacity screen applying Kentucky v. Graham (1985) and Ex parte Young (1908). "
            "Not legal advice. Consult counsel for final defendant identification and pleading strategy."
        ),
    }
