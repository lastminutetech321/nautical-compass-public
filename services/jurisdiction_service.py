"""
Jurisdiction analysis applying:
  28 U.S.C. §1331 — federal question jurisdiction (arising under Constitution or federal law)
  28 U.S.C. §1343 — civil rights jurisdiction (§1983 and related statutes)
  28 U.S.C. §1367 — supplemental jurisdiction over related state-law claims
  28 U.S.C. §1391 — general venue statute
  Merrell Dow Pharmaceuticals v. Thompson, 478 U.S. 804 (1986) — federal question must appear on face of well-pleaded complaint
"""
from typing import Any, Dict, List, Optional

CASE_LAW = [
    "28 U.S.C. §1331 — federal question jurisdiction",
    "28 U.S.C. §1343 — civil rights jurisdiction",
    "28 U.S.C. §1367 — supplemental jurisdiction",
    "28 U.S.C. §1391 — venue",
    "Merrell Dow Pharmaceuticals v. Thompson, 478 U.S. 804 (1986)",
    "Grable & Sons Metal Products v. Darue Engineering, 545 U.S. 308 (2005)",
]


class JurisdictionServiceError(Exception):
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


def _build_text(complaint: Dict[str, Any]) -> str:
    fields = [
        complaint.get("category", ""),
        complaint.get("subcategory", ""),
        complaint.get("shortTitle", ""),
        complaint.get("plainLanguageSummary", ""),
        complaint.get("whatHappened", ""),
        complaint.get("desiredOutcome", ""),
    ]
    return " ".join(f or "" for f in fields).lower()


def _analyze_federal_question(complaint: Dict[str, Any], target_type: str, text: str) -> Dict[str, Any]:
    """
    28 U.S.C. §1331: District courts have original jurisdiction of all civil actions arising
    under the Constitution, laws, or treaties of the United States.
    Merrell Dow / Grable: the federal issue must be necessarily raised, actually disputed,
    substantial, and capable of resolution without disrupting federal-state balance.
    """
    federal_triggers = [
        "civil rights", "constitutional", "§1983", "1983", "fourth amendment",
        "fourteenth amendment", "due process", "equal protection", "first amendment",
        "fifth amendment", "federal law", "federal statute", "fcra", "fdcpa",
        "title vii", "ada", "fmla", "erisa", "section 1983",
    ]
    matched = [t for t in federal_triggers if t in text]

    if target_type == "government":
        matched.append("government actor — federal constitutional claim on face of complaint")

    basis_items: List[str] = []
    if target_type == "government":
        basis_items.append(
            "Constitutional claims against government actors arise under federal law — §1331 jurisdiction established "
            "on face of well-pleaded complaint. Merrell Dow, 478 U.S. 804 (1986)."
        )
    if any(t in text for t in ["§1983", "1983", "civil rights", "section 1983"]):
        basis_items.append("42 U.S.C. §1983 claim — federal statute, §1331 jurisdiction confirmed.")
    if any(t in text for t in ["fcra", "credit reporting", "consumer report"]):
        basis_items.append("FCRA claim (15 U.S.C. §1681) — federal statute, §1331 jurisdiction confirmed.")
    if any(t in text for t in ["fdcpa", "debt collection"]):
        basis_items.append("FDCPA claim (15 U.S.C. §1692) — federal statute, §1331 jurisdiction confirmed.")

    federal_question = target_type == "government" or bool(matched) or bool(basis_items)

    return {
        "established": federal_question,
        "trigger_terms": list(set(matched))[:5],
        "basis": basis_items if basis_items else (
            ["No clear federal question identified from the intake facts."] if not federal_question else []
        ),
        "analysis": (
            f"PASS — Federal question jurisdiction under 28 U.S.C. §1331 established. "
            f"{' '.join(basis_items[:1]) if basis_items else 'Federal constitutional or statutory claim present.'}"
            if federal_question else
            "FAIL — No federal question identified. Case may need to proceed in state court unless "
            "diversity jurisdiction (28 U.S.C. §1332) applies ($75,000+ in controversy, parties from different states)."
        ),
    }


def _analyze_civil_rights_jurisdiction(complaint: Dict[str, Any], target_type: str, text: str) -> Dict[str, Any]:
    """
    28 U.S.C. §1343(a)(3): District courts have original jurisdiction over actions to redress
    deprivation of civil rights under color of state authority under 42 U.S.C. §1983.
    §1343(a)(4): Actions to recover damages under federal civil rights laws.
    This is a specialized jurisdictional grant that parallels §1331 for civil rights claims.
    """
    civil_rights_terms = [
        "§1983", "1983", "civil rights", "color of law", "constitutional violation",
        "police", "officer", "government actor", "state actor", "section 1983",
    ]
    matched = [t for t in civil_rights_terms if t in text]

    established = target_type == "government" or bool(matched)

    basis: List[str] = []
    if target_type == "government":
        basis.append(
            "28 U.S.C. §1343(a)(3): Original jurisdiction for claims that a government actor "
            "deprived plaintiff of constitutional rights under color of state law."
        )
    if any(t in text for t in ["§1983", "1983", "section 1983"]):
        basis.append("28 U.S.C. §1343(a)(3)–(4): Direct jurisdictional grant for §1983 claims.")

    return {
        "established": established,
        "basis": basis,
        "analysis": (
            f"PASS — Civil rights jurisdiction under 28 U.S.C. §1343 applies. "
            f"{basis[0] if basis else 'Government actor and civil rights claim present.'}"
            if established else
            "Civil rights jurisdiction under §1343 not established — no government actor or §1983 claim detected."
        ),
    }


def _analyze_supplemental_jurisdiction(intake_state: Dict[str, Any], complaint: Dict[str, Any], text: str) -> Dict[str, Any]:
    """
    28 U.S.C. §1367: When a district court has original jurisdiction, it may exercise supplemental
    jurisdiction over all other claims so related that they form part of the same case or controversy.
    """
    state_law_terms = [
        "breach of contract", "negligence", "fraud", "assault", "battery",
        "trespass", "defamation", "intentional infliction", "state law",
        "tort", "negligent",
    ]
    state_claims = [t for t in state_law_terms if t in text]

    if not state_claims:
        return {"available": False, "analysis": "No state-law claims detected — supplemental jurisdiction not relevant."}

    return {
        "available": True,
        "state_law_indicators": state_claims,
        "analysis": (
            f"Supplemental jurisdiction under 28 U.S.C. §1367 available for state-law claims "
            f"({', '.join(state_claims[:3])}) arising from the same transaction or occurrence. "
            "Federal court may hear these alongside the federal claims without separate jurisdictional basis."
        ),
    }


def _recommend_venue(complaint: Dict[str, Any], federal_question: bool) -> str:
    """
    28 U.S.C. §1391(b): Venue proper in (1) district where defendant resides,
    (2) district where substantial events occurred, or (3) any district where defendant subject to personal jurisdiction.
    """
    target_name = complaint.get("targetName", "") or ""
    if federal_question:
        return (
            f"Federal district court recommended. 28 U.S.C. §1391(b): venue proper in the district "
            f"where {target_name or 'defendant'} resides or where the events giving rise to the claim occurred. "
            "File in the U.S. District Court for the district covering the location of the alleged conduct."
        )
    return (
        "State court recommended for state-law claims without a federal question. "
        "Consider the state trial court of general jurisdiction in the county where events occurred."
    )


def analyze_jurisdiction(intake_state: Dict[str, Any], complaint_id: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise JurisdictionServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise JurisdictionServiceError("No complaints found in intake_state.")

    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise JurisdictionServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    target_type = _normalize_target_type(complaint)
    text = _build_text(complaint)

    federal_q = _analyze_federal_question(complaint, target_type, text)
    civil_rights_j = _analyze_civil_rights_jurisdiction(complaint, target_type, text)
    supplemental = _analyze_supplemental_jurisdiction(intake_state, complaint, text)

    recommended_court = (
        "federal_district"
        if federal_q["established"] or civil_rights_j["established"]
        else "state_court"
    )

    return {
        "complaintId": complaint.get("complaintId", ""),
        "targetName": complaint.get("targetName", ""),
        "category": complaint.get("category", ""),
        "target_type": target_type,
        "federal_question": federal_q["established"],
        "federal_question_analysis": federal_q["analysis"],
        "federal_question_basis": federal_q["basis"],
        "civil_rights_jurisdiction": civil_rights_j["established"],
        "civil_rights_jurisdiction_analysis": civil_rights_j["analysis"],
        "supplemental_jurisdiction": supplemental,
        "recommended_court": recommended_court,
        "venue_notes": _recommend_venue(complaint, federal_q["established"]),
        "case_law": CASE_LAW,
        "note": (
            "Intake-level jurisdiction screen applying 28 U.S.C. §1331 and §1343. "
            "Not legal advice or a final jurisdiction determination. Consult counsel for filing strategy."
        ),
    }
