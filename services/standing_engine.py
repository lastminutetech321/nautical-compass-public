"""
Standing Engine — core Article III standing analysis.
Injury: Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992)
Ex parte Young doctrine for ongoing government violations.
"""
from typing import Any, Dict, List


def _str(val: Any) -> str:
    return (val or "").strip()


def _bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


def analyze_injury(data: Dict[str, Any]) -> Dict[str, Any]:
    harm = _str(data.get("harm_description"))
    harm_type = _str(data.get("harm_type")).lower()

    exists = bool(harm)
    valid_types = {"economic", "physical", "constitutional"}
    is_valid = harm_type in valid_types if exists else False

    return {
        "injury_exists": exists,
        "harm_type": harm_type or None,
        "is_valid_injury": is_valid,
        "notes": harm if exists else "No harm description provided.",
    }


def analyze_causation(data: Dict[str, Any]) -> Dict[str, Any]:
    defendant_type = _str(data.get("defendant_type"))
    actor_type = _str(data.get("actor_type"))

    established = bool(defendant_type) and bool(actor_type)

    return {
        "causation_established": established,
        "defendant_type": defendant_type or None,
        "actor_type": actor_type or None,
        "notes": (
            f"Actor '{actor_type}' caused harm via defendant '{defendant_type}'."
            if established
            else "Missing actor_type or defendant_type; causation not established."
        ),
    }


def analyze_redressability(data: Dict[str, Any]) -> Dict[str, Any]:
    relief = _str(data.get("requested_relief"))
    redressable = bool(relief)

    return {
        "redressability_met": redressable,
        "requested_relief": relief or None,
        "notes": (
            f"Relief requested: {relief}."
            if redressable
            else "No requested_relief provided; redressability not met."
        ),
    }


def analyze_capacity(data: Dict[str, Any]) -> Dict[str, Any]:
    government_actor = _bool(data.get("government_actor", False))
    ongoing_violation = _bool(data.get("ongoing_violation", False))

    if government_actor:
        capacity_type = "official"
        doctrines = ["Ex parte Young"] if ongoing_violation else []
    else:
        capacity_type = "individual"
        doctrines = []

    return {
        "capacity_type": capacity_type,
        "government_actor": government_actor,
        "ongoing_violation": ongoing_violation,
        "applicable_doctrines": doctrines,
    }


def build_claims(data: Dict[str, Any]) -> List[Dict[str, str]]:
    harm_type = _str(data.get("harm_type")).lower()
    government_actor = _bool(data.get("government_actor", False))

    claims: List[Dict[str, str]] = []

    if harm_type == "economic":
        claims.append({
            "claim": "Breach of Contract",
            "basis": "Economic harm indicating contractual duty violation.",
        })
        claims.append({
            "claim": "Unjust Enrichment",
            "basis": "Defendant received benefit at plaintiff's economic expense.",
        })

    if harm_type == "constitutional" and government_actor:
        claims.append({
            "claim": "42 U.S.C. § 1983 — Civil Rights Violation",
            "basis": "Constitutional harm by a government actor acting under color of law.",
        })

    return claims
