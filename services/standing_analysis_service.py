"""
Standing analysis applying:
  Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992) — three-element Article III test
  TransUnion LLC v. Ramirez, 594 U.S. 413 (2021) — concrete harm required; bare statutory violation insufficient
  Spokeo, Inc. v. Robins, 578 U.S. 330 (2016) — injury must be both concrete and particularized
"""
from typing import Any, Dict, List, Optional

CASE_LAW = [
    "Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992)",
    "TransUnion LLC v. Ramirez, 594 U.S. 413 (2021)",
    "Spokeo, Inc. v. Robins, 578 U.S. 330 (2016)",
]


class StandingAnalysisServiceError(Exception):
    pass


def _safe_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _analyze_injury_in_fact(complaint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lujan element 1: injury in fact — concrete, particularized, actual or imminent.
    TransUnion: a bare procedural or statutory violation without real-world harm does not satisfy
    Article III. Plaintiff must show harm with close relationship to harms recognized at common law.
    Spokeo: injury must be both concrete (real, not abstract) and particularized (individual, not diffuse).
    """
    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    work_loss = _safe_number(complaint.get("workLossAmount"))
    time_lost = _safe_number(complaint.get("timeLostHours"))
    injury_claimed = _safe_bool(complaint.get("injuryClaimed"))
    property_damage = _safe_bool(complaint.get("propertyDamageClaimed"))
    credit_impact = _safe_bool(complaint.get("creditImpactClaimed"))
    emotional_stress = _safe_bool(complaint.get("emotionalStressClaimed"))
    short_title = complaint.get("shortTitle", "") or ""
    what_happened = complaint.get("whatHappened", "") or ""
    summary = complaint.get("plainLanguageSummary", "") or ""

    concrete_harms: List[str] = []
    if financial_loss > 0:
        concrete_harms.append(f"monetary loss of ${financial_loss:,.0f} (tangible economic harm)")
    if work_loss > 0:
        concrete_harms.append(f"work/income loss of ${work_loss:,.0f} (tangible economic harm)")
    if injury_claimed:
        concrete_harms.append("physical injury (traditional common-law harm)")
    if property_damage:
        concrete_harms.append("property damage (traditional common-law harm)")
    if credit_impact:
        # TransUnion held that dissemination of false credit info to third parties is concrete harm;
        # internal file inaccuracy alone (never disclosed) is not.
        concrete_harms.append(
            "credit harm — concrete if information was disclosed to third parties (TransUnion, 594 U.S. at 433); "
            "weak if harm is solely internal file inaccuracy not yet disclosed"
        )
    if time_lost > 0:
        concrete_harms.append(f"time lost ({time_lost:.0f} hours — opportunity cost, supports concreteness)")
    if emotional_stress and not concrete_harms:
        concrete_harms.append(
            "emotional distress alone — generally insufficient without accompanying tangible harm "
            "unless tied to a recognized intentional tort (TransUnion)"
        )

    strong_concrete = any(
        "monetary" in h or "physical" in h or "property" in h or "income" in h
        for h in concrete_harms
    )
    concrete = len(concrete_harms) > 0 and (strong_concrete or credit_impact)

    has_narrative = bool(short_title or what_happened or summary)
    particularized = has_narrative and concrete

    actual_or_imminent = (
        financial_loss > 0 or work_loss > 0 or injury_claimed
        or property_damage or credit_impact or time_lost > 0
    )

    met = concrete and particularized and actual_or_imminent

    if met:
        analysis = (
            f"PASS — Injury in fact established under Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992). "
            f"Concrete harm present: {'; '.join(concrete_harms[:2])}. "
            "Harm is particularized to this plaintiff and has already occurred (actual, not merely imminent). "
            "Under TransUnion LLC v. Ramirez, 594 U.S. 413 (2021), real-world harm beyond any statutory violation "
            "is present."
        )
    elif concrete_harms and not particularized:
        analysis = (
            "PARTIAL — Concrete harm indicators present but factual narrative is thin. "
            "Under Spokeo, Inc. v. Robins, 578 U.S. 330 (2016), injury must be both concrete and particularized. "
            "Strengthen the complaint with specific facts connecting the harm to this plaintiff."
        )
    elif emotional_stress and not strong_concrete:
        analysis = (
            "FAIL — Emotional distress without accompanying tangible harm is insufficient under "
            "TransUnion LLC v. Ramirez, 594 U.S. 413 (2021). Plaintiff must allege harm with a close "
            "relationship to harms traditionally recognized at common law (physical injury, property damage, "
            "financial loss, defamation)."
        )
    else:
        analysis = (
            "FAIL — No concrete harm established. TransUnion requires more than a bare procedural violation. "
            "Add financial loss, physical injury, property damage, or credit impact to establish Article III standing."
        )

    return {
        "met": met,
        "concrete": concrete,
        "particularized": particularized,
        "actual_or_imminent": actual_or_imminent,
        "concrete_harms": concrete_harms,
        "analysis": analysis,
    }


def _analyze_causation(complaint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lujan element 2: causation — injury must be fairly traceable to the defendant's conduct,
    not the result of the independent action of some third party not before the court.
    """
    target_name = complaint.get("targetName", "") or ""
    target_person = complaint.get("targetPerson", "") or ""
    target_department = complaint.get("targetDepartment", "") or ""
    what_happened = complaint.get("whatHappened", "") or ""
    what_was_said = complaint.get("whatWasSaid", "") or ""
    user_actions = complaint.get("userActionsTaken", []) or []

    factors: List[str] = []
    if target_name:
        factors.append(f"named defendant: {target_name}")
    if target_person:
        factors.append(f"named individual actor: {target_person}")
    if target_department:
        factors.append(f"identified department or agency: {target_department}")
    if what_happened:
        factors.append("conduct narrative directly connecting defendant's actions to plaintiff's harm")
    if what_was_said:
        factors.append("statements or communications attributed to defendant on the record")
    if user_actions:
        factors.append(
            f"plaintiff documented {len(user_actions)} follow-up action(s), "
            "supporting the traceability chain"
        )

    met = bool(target_name) and bool(what_happened)

    if met:
        analysis = (
            f"PASS — Causation satisfied under Lujan. Injury is fairly traceable to {target_name}'s conduct. "
            f"Traceability factors: {'; '.join(factors)}. "
            "No independent third-party causal chain apparent from the intake record."
        )
    elif target_name and not what_happened:
        analysis = (
            f"PARTIAL — Defendant identified ({target_name}) but no conduct narrative provided. "
            "Lujan requires the injury be 'fairly traceable to the challenged action of the defendant.' "
            "Add 'whatHappened' to establish the factual causal chain."
        )
    else:
        analysis = (
            "FAIL — Causation cannot be assessed without a named defendant and a conduct narrative. "
            "Lujan v. Defenders of Wildlife requires that the injury be fairly traceable to the defendant's "
            "challenged conduct, not merely a background condition or third-party action."
        )

    return {
        "met": met,
        "factors": factors,
        "analysis": analysis,
    }


def _analyze_redressability(complaint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lujan element 3: redressability — it must be likely, not merely speculative, that
    a favorable court decision would redress the plaintiff's injury.
    """
    desired_outcome = complaint.get("desiredOutcome", "") or ""
    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    work_loss = _safe_number(complaint.get("workLossAmount"))
    prior_complaint = _safe_bool(complaint.get("priorComplaintMade"))
    desired_lower = desired_outcome.lower()

    remedies: List[str] = []
    if financial_loss > 0 or work_loss > 0:
        total = financial_loss + work_loss
        remedies.append(f"compensatory damages for alleged financial loss (${total:,.0f}) — court can award")
    if any(t in desired_lower for t in ["payment", "refund", "compensation", "damages", "reimburse"]):
        remedies.append("monetary relief specifically requested — court has authority to award")
    if any(t in desired_lower for t in ["stop", "injunction", "cease", "enjoin", "prevent", "policy"]):
        remedies.append("prospective injunctive relief sought — court can order cessation or policy change")
    if any(t in desired_lower for t in ["record", "correct", "expunge", "remove", "retract"]):
        remedies.append("declaratory or corrective relief — court can order correction")
    if prior_complaint:
        remedies.append("prior demand documented, showing plaintiff sought relief from defendant first")
    if desired_outcome and not remedies:
        short = desired_outcome[:100]
        remedies.append(f"requested outcome stated ('{short}') — court may have equitable or legal authority to provide relief")

    met = bool(remedies)

    if met:
        analysis = (
            "PASS — Redressability satisfied under Lujan. A favorable court decision would likely redress "
            f"plaintiff's injury. Available relief paths: {'; '.join(remedies[:2])}."
        )
    else:
        analysis = (
            "FAIL — Redressability is uncertain. Under Lujan v. Defenders of Wildlife, it must be 'likely, "
            "as opposed to merely speculative, that the injury will be redressed by a favorable decision.' "
            "Plaintiff has not stated a desired outcome or a form of relief that a court could provide."
        )

    return {
        "met": met,
        "available_remedies": remedies,
        "analysis": analysis,
    }


def analyze_standing(intake_state: Dict[str, Any], complaint_id: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise StandingAnalysisServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise StandingAnalysisServiceError("No complaints found in intake_state.")

    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise StandingAnalysisServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    injury = _analyze_injury_in_fact(complaint)
    causation = _analyze_causation(complaint)
    redressability = _analyze_redressability(complaint)

    standing = injury["met"] and causation["met"] and redressability["met"]

    if standing:
        standing_label = "standing_established"
    elif injury["met"] and causation["met"]:
        standing_label = "standing_likely_with_remedy_clarification"
    elif injury["met"]:
        standing_label = "standing_needs_causation_and_remedy"
    else:
        standing_label = "standing_not_established"

    return {
        "complaintId": complaint.get("complaintId", ""),
        "injury_in_fact": injury,
        "causation": causation,
        "redressability": redressability,
        "standing": standing,
        "standing_label": standing_label,
        "case_law": CASE_LAW,
        "note": (
            "Intake-level standing screen applying Lujan v. Defenders of Wildlife (1992) and "
            "TransUnion LLC v. Ramirez (2021). Not legal advice or a final court determination."
        ),
    }
