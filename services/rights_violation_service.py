"""
Rights violation analysis applying:
  42 U.S.C. §1983 — civil rights claim under color of state law
  Monell v. Dept. of Social Services, 436 U.S. 658 (1978) — municipal liability via policy/custom
  U.S. Const. amend. IV — unreasonable searches and seizures
  U.S. Const. amend. XIV — due process (substantive + procedural), equal protection
  West v. Atkins, 487 U.S. 42 (1988) — acting under color of state law
  City of Canton v. Harris, 489 U.S. 378 (1989) — failure to train as municipal policy
"""
from typing import Any, Dict, List, Optional

CASE_LAW = [
    "42 U.S.C. §1983",
    "Monell v. Dept. of Social Services, 436 U.S. 658 (1978)",
    "U.S. Const. amend. IV (Fourth Amendment — search and seizure)",
    "U.S. Const. amend. XIV (Fourteenth Amendment — due process, equal protection)",
    "West v. Atkins, 487 U.S. 42 (1988) — color of state law",
    "City of Canton v. Harris, 489 U.S. 378 (1989) — failure to train",
]


class RightsViolationServiceError(Exception):
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


def _is_municipal(complaint: Dict[str, Any]) -> bool:
    target_name = (complaint.get("targetName", "") or "").lower()
    municipal_terms = ["city", "county", "municipality", "police department", "school district", "board"]
    return any(t in target_name for t in municipal_terms)


def _build_text(complaint: Dict[str, Any]) -> str:
    fields = [
        complaint.get("category", ""),
        complaint.get("subcategory", ""),
        complaint.get("shortTitle", ""),
        complaint.get("plainLanguageSummary", ""),
        complaint.get("whatHappened", ""),
        complaint.get("whatWasSaid", ""),
        complaint.get("desiredOutcome", ""),
    ]
    return " ".join(f or "" for f in fields).lower()


def _detect_fourth_amendment(text: str, target_type: str) -> Optional[Dict[str, Any]]:
    fourth_terms = [
        "search", "seizure", "seized", "detained", "detention", "arrested", "arrest",
        "stopped", "stop", "property taken", "searched", "warrant", "warrantless",
        "unreasonable", "pat down", "frisk",
    ]
    if target_type != "government":
        return None
    matched = [t for t in fourth_terms if t in text]
    if not matched:
        return None
    return {
        "amendment": "Fourth Amendment",
        "clause": "Unreasonable Searches and Seizures — U.S. Const. amend. IV",
        "trigger_terms": matched[:4],
        "analysis": (
            "Fourth Amendment claim indicated. Government conduct involving search, seizure, detention, "
            "or arrest without valid warrant or probable cause is presumptively unreasonable. "
            "Plaintiff must show (1) a Fourth Amendment 'search' or 'seizure' occurred, "
            "(2) conducted by a government actor, and (3) it was unreasonable. "
            "Evidence of warrantless search or pretextual stop strengthens the claim."
        ),
    }


def _detect_fourteenth_due_process(text: str, target_type: str) -> Optional[Dict[str, Any]]:
    dp_terms = [
        "due process", "hearing", "notice", "deprived", "deprivation", "policy",
        "license", "benefit", "terminated", "denied", "without notice", "no hearing",
        "arbitrary", "punishment",
    ]
    if target_type != "government":
        return None
    matched = [t for t in dp_terms if t in text]
    if not matched:
        return None

    substantive = any(t in text for t in ["arbitrary", "punishment", "excessive force", "shock the conscience"])
    clause = "Substantive Due Process" if substantive else "Procedural Due Process"
    analysis = (
        f"Fourteenth Amendment — {clause} claim indicated. "
    )
    if substantive:
        analysis += (
            "Substantive due process protects against government action that 'shocks the conscience' or "
            "is arbitrary deprivation of a fundamental right. Rochin v. California, 342 U.S. 165 (1952)."
        )
    else:
        analysis += (
            "Procedural due process requires that before the government deprives a person of life, liberty, "
            "or property, it must provide adequate notice and an opportunity to be heard. "
            "Mathews v. Eldridge, 424 U.S. 319 (1976): balance individual interest, risk of error, and government interest."
        )

    return {
        "amendment": "Fourteenth Amendment",
        "clause": clause,
        "trigger_terms": matched[:4],
        "analysis": analysis,
    }


def _detect_fourteenth_equal_protection(text: str, target_type: str) -> Optional[Dict[str, Any]]:
    ep_terms = [
        "discrimination", "discriminated", "unequal", "selective", "targeted",
        "race", "racial", "gender", "sex", "class", "equal protection",
        "similarly situated", "treated differently",
    ]
    if target_type != "government":
        return None
    matched = [t for t in ep_terms if t in text]
    if not matched:
        return None
    return {
        "amendment": "Fourteenth Amendment",
        "clause": "Equal Protection Clause — U.S. Const. amend. XIV, §1",
        "trigger_terms": matched[:4],
        "analysis": (
            "Equal Protection claim indicated. Government must treat similarly situated persons alike. "
            "Plaintiff must show (1) intentional discrimination, (2) by a government actor, "
            "(3) based on a protected class (strict/intermediate scrutiny) or with no rational basis. "
            "Village of Arlington Heights v. Metro. Housing Dev. Corp., 429 U.S. 252 (1977): "
            "discriminatory intent, not just disparate impact, required."
        ),
    }


def _detect_section_1983(
    text: str,
    target_type: str,
    constitutional_violations: List[Dict[str, Any]],
    complaint: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    §1983 requires: (1) defendant acted under color of state law; (2) deprived plaintiff of a right
    secured by the Constitution or federal law. West v. Atkins (1988).
    """
    if target_type != "government":
        return None
    if not constitutional_violations:
        color_terms = ["officer", "police", "department", "agency", "official", "state", "government"]
        if not any(t in text for t in color_terms):
            return None

    target_name = complaint.get("targetName", "") or ""
    target_person = complaint.get("targetPerson", "") or ""
    against = []
    if target_person:
        against.append(f"{target_person} (individual capacity — personal liability under §1983)")
    if target_name:
        against.append(f"{target_name} (if municipal entity, subject to Monell policy/custom requirement)")

    viol_names = [v["clause"] for v in constitutional_violations]
    basis = (
        f"Government actor acting under color of state law allegedly deprived plaintiff of "
        f"constitutional rights: {'; '.join(viol_names) if viol_names else 'rights to be specified'}. "
        "West v. Atkins, 487 U.S. 42 (1988): acting under color of state law includes conduct "
        "taken under authority of state law, even if that authority is abused."
    )

    return {
        "type": "§1983 Civil Rights Claim",
        "statute": "42 U.S.C. §1983",
        "basis": basis,
        "against": against,
        "color_of_law": True,
        "analysis": (
            "§1983 claim supported. Elements: (1) defendant acted under color of state law — "
            "government actor present; (2) deprivation of a federally protected right — constitutional "
            f"violations detected: {', '.join(viol_names) or 'specify constitutional right'}. "
            "Note: §1983 itself creates no substantive rights — it provides a remedy for violation of "
            "rights established elsewhere (Constitution, federal statutes)."
        ),
    }


def _analyze_municipal_liability(
    complaint: Dict[str, Any],
    claims: List[Dict[str, Any]],
    target_type: str,
) -> Dict[str, Any]:
    """
    Monell (1978): municipalities are 'persons' under §1983 but liability requires showing
    an official policy or custom was the 'moving force' behind the constitutional violation.
    Respondeat superior is not enough — the policy/custom must be the direct cause.
    City of Canton (1989): failure to train employees can be a policy if the need for training
    was 'so obvious' that failure amounts to deliberate indifference.
    """
    if target_type != "government" or not _is_municipal(complaint):
        return {
            "applies": False,
            "analysis": "Municipal liability analysis not applicable — target is not a municipality.",
        }

    text = _build_text(complaint)
    policy_terms = [
        "policy", "custom", "practice", "training", "failure to train",
        "pattern", "widespread", "deliberate indifference", "procedure",
    ]
    policy_indicators = [t for t in policy_terms if t in text]
    has_1983_claim = any(c.get("type", "").startswith("§1983") for c in claims)

    if not has_1983_claim:
        return {
            "applies": False,
            "analysis": "Municipal liability requires a §1983 claim as the predicate.",
        }

    if policy_indicators:
        analysis = (
            f"MUNICIPAL LIABILITY INDICATED — Monell v. Dept. of Social Services, 436 U.S. 658 (1978). "
            f"Policy/custom indicators present: {', '.join(policy_indicators)}. "
            "Plaintiff must show the municipality had an official policy or entrenched custom that was "
            "the 'moving force' behind the constitutional violation. "
            "City of Canton v. Harris, 489 U.S. 378 (1989): failure to train is actionable if the need "
            "was obvious and the failure amounts to deliberate indifference to constitutional rights."
        )
        applies = True
    else:
        analysis = (
            "MUNICIPAL LIABILITY POSSIBLE but policy/custom evidence is thin in the intake record. "
            "Monell bars respondeat superior — plaintiff cannot recover from a municipality simply because "
            "it employed the wrongdoer. Allege a specific policy, custom, or failure-to-train claim to proceed."
        )
        applies = True

    return {"applies": applies, "policy_indicators": policy_indicators, "analysis": analysis}


def _detect_private_claims(text: str, complaint: Dict[str, Any]) -> List[Dict[str, Any]]:
    claims = []
    if any(t in text for t in ["credit", "reporting", "consumer report", "credit score", "bureau", "fcra"]):
        claims.append({
            "type": "FCRA Claim",
            "statute": "Fair Credit Reporting Act, 15 U.S.C. §1681",
            "basis": "Inaccurate consumer report information or unauthorized access to consumer credit file.",
            "against": [complaint.get("targetName", "credit agency or furnisher")],
            "analysis": (
                "FCRA claim indicated. Plaintiff may have a private right of action for willful or negligent "
                "violations. Remedy includes actual damages, statutory damages ($100–$1,000 per willful violation), "
                "punitive damages, and attorney's fees. 15 U.S.C. §1681n–§1681o."
            ),
        })
    if any(t in text for t in ["debt", "collector", "collection", "harassment", "fdcpa", "owed"]):
        claims.append({
            "type": "FDCPA Claim",
            "statute": "Fair Debt Collection Practices Act, 15 U.S.C. §1692",
            "basis": "Debt collector engaged in abusive, deceptive, or unfair collection practices.",
            "against": [complaint.get("targetName", "debt collector")],
            "analysis": (
                "FDCPA claim indicated. Applies to third-party debt collectors, not original creditors. "
                "Prohibited conduct includes harassment, false representations, and unfair practices. "
                "Statutory damages up to $1,000, actual damages, and attorney's fees. 15 U.S.C. §1692k."
            ),
        })
    if any(t in text for t in ["payment", "invoice", "contract", "breach", "nonpayment", "refund"]):
        claims.append({
            "type": "Breach of Contract / Unjust Enrichment",
            "statute": "State contract law (varies by jurisdiction)",
            "basis": "Failure to pay for services rendered or breach of contractual obligation.",
            "against": [complaint.get("targetName", "contracting party")],
            "analysis": (
                "Breach of contract or unjust enrichment claim indicated. Elements: (1) valid contract, "
                "(2) plaintiff performance, (3) defendant breach, (4) resulting damages. "
                "If no written contract, unjust enrichment (quantum meruit) may allow recovery for "
                "reasonable value of services rendered."
            ),
        })
    return claims


def analyze_rights_violations(intake_state: Dict[str, Any], complaint_id: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise RightsViolationServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise RightsViolationServiceError("No complaints found in intake_state.")

    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise RightsViolationServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    target_type = _normalize_target_type(complaint)
    text = _build_text(complaint)

    constitutional_violations: List[Dict[str, Any]] = []
    claims: List[Dict[str, Any]] = []

    if target_type == "government":
        for detector in [_detect_fourth_amendment, _detect_fourteenth_due_process, _detect_fourteenth_equal_protection]:
            result = detector(text, target_type)
            if result:
                constitutional_violations.append(result)

        section_1983 = _detect_section_1983(text, target_type, constitutional_violations, complaint)
        if section_1983:
            claims.append(section_1983)
    else:
        claims.extend(_detect_private_claims(text, complaint))

    municipal = _analyze_municipal_liability(complaint, claims, target_type)

    severity_score = min(100, len(constitutional_violations) * 20 + len(claims) * 15)
    if _safe_number(complaint.get("financialLossAmount")) > 0:
        severity_score = min(100, severity_score + 15)
    if _safe_bool(complaint.get("injuryClaimed")):
        severity_score = min(100, severity_score + 20)

    if severity_score >= 60:
        severity_label = "strong_issue_signal"
    elif severity_score >= 30:
        severity_label = "moderate_issue_signal"
    elif severity_score > 0:
        severity_label = "weak_issue_signal"
    else:
        severity_label = "unclear_issue_signal"

    return {
        "complaintId": complaint.get("complaintId", ""),
        "targetName": complaint.get("targetName", ""),
        "target_type": target_type,
        "claims": claims,
        "constitutional_violations": constitutional_violations,
        "municipal_liability": municipal.get("applies", False),
        "municipal_liability_analysis": municipal.get("analysis", ""),
        "severity_score": severity_score,
        "severity_label": severity_label,
        "case_law": CASE_LAW,
        "note": (
            "Intake-level rights and claim-spotting screen applying §1983, Monell (1978), "
            "Fourth and Fourteenth Amendment doctrine. Not legal advice or a final merits determination."
        ),
    }
