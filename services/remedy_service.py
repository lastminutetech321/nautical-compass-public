"""
Remedy analysis service — Phase 3C.

Determines available relief from intake facts and legal_results output:
  compensatory damages, punitive damages, injunctive relief, declaratory
  relief, record correction / document production, attorney's fees
  (only where legally authorized), and costs.

Key authority:
  Newport v. Fact Concerts, Inc., 453 U.S. 247 (1981)
    — municipalities NOT liable for punitive damages under §1983
  Smith v. Wade, 461 U.S. 30 (1983)
    — punitive damages available against individual-capacity §1983 defendants
  Ex parte Young, 209 U.S. 123 (1908)
    — injunctive relief against state officers despite Eleventh Amendment
  42 U.S.C. §1988 — attorney's fees for prevailing party in §1983 actions
  28 U.S.C. §2201 — Declaratory Judgment Act
  15 U.S.C. §1681n/o — FCRA statutory damages and attorney's fees
  15 U.S.C. §1692k — FDCPA statutory damages and attorney's fees
  Fed. R. Civ. P. 54(d) — taxable costs for prevailing party
"""
from typing import Any, Dict, List, Optional


CASE_LAW = [
    "Newport v. Fact Concerts, Inc., 453 U.S. 247 (1981)",
    "Smith v. Wade, 461 U.S. 30 (1983)",
    "Ex parte Young, 209 U.S. 123 (1908)",
    "42 U.S.C. §1988 (Civil Rights Attorney's Fees Awards Act)",
    "28 U.S.C. §2201 (Declaratory Judgment Act)",
    "15 U.S.C. §1681n/o (FCRA damages and fees)",
    "15 U.S.C. §1692k (FDCPA damages and fees)",
    "Fed. R. Civ. P. 54(d) (costs for prevailing party)",
]


class RemedyServiceError(Exception):
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


def _need(label: str) -> str:
    return f"[FACT NEEDED: {label}]"


def _build_text(complaint: Dict[str, Any]) -> str:
    fields = [
        complaint.get("category", ""),
        complaint.get("shortTitle", ""),
        complaint.get("plainLanguageSummary", ""),
        complaint.get("whatHappened", ""),
        complaint.get("desiredOutcome", ""),
    ]
    return " ".join(f or "" for f in fields).lower()


def _has_claim_type(legal_results: Dict[str, Any], prefix: str) -> bool:
    claims = legal_results.get("rights", {}).get("claims", [])
    return any(c.get("type", "").startswith(prefix) for c in claims)


# ---------------------------------------------------------------------------
# Relief item builders — each returns a dict with type/label/amount/basis/note
# ---------------------------------------------------------------------------

def _compensatory(financial_loss: float) -> Dict[str, Any]:
    if financial_loss > 0:
        return {
            "type": "compensatory",
            "label": "Compensatory damages",
            "amount_display": (
                f"not less than ${financial_loss:,.2f}, "
                "plus additional compensatory and consequential damages to be proven at trial"
            ),
            "legal_basis": "Common law; 42 U.S.C. §1983",
            "note": "Plaintiff-stated figure. Verify with records and receipts before filing.",
        }
    return {
        "type": "compensatory",
        "label": "Compensatory damages",
        "amount_display": _need(
            "total compensatory damages — quantify all economic loss, non-economic harm, "
            "and consequential damages with supporting records"
        ),
        "legal_basis": "Common law; 42 U.S.C. §1983",
        "note": "No dollar amount stated. Document all losses before filing.",
    }


def _punitive_individual(individual_defendants: List[str]) -> Dict[str, Any]:
    against = ", ".join(individual_defendants) if individual_defendants else "individual Defendant(s)"
    return {
        "type": "punitive",
        "label": f"Punitive damages against {against}",
        "amount_display": _need(
            "punitive damages amount — proportional to egregiousness of conduct and deterrence need"
        ),
        "legal_basis": "Smith v. Wade, 461 U.S. 30 (1983)",
        "note": (
            "Punitive damages available against individual-capacity defendants under §1983. "
            "Newport v. Fact Concerts, 453 U.S. 247 (1981): municipalities are NOT subject to "
            "punitive damages. Plead the defendant's subjective malice, reckless disregard, or "
            "callous indifference to established rights."
        ),
    }


def _punitive_private() -> Dict[str, Any]:
    return {
        "type": "punitive",
        "label": "Punitive damages",
        "amount_display": _need(
            "punitive damages amount — based on willfulness or reckless disregard of plaintiff's rights"
        ),
        "legal_basis": "State tort law (standard varies by jurisdiction)",
        "note": (
            "Private actor — punitive damages governed by applicable state law standard. "
            "Plead specific willful, malicious, or reckless conduct to support punitive request."
        ),
    }


def _punitive_unavailable_note() -> Dict[str, Any]:
    return {
        "type": "punitive_unavailable",
        "label": "Punitive damages — NOT AVAILABLE against this Defendant",
        "amount_display": None,
        "legal_basis": "Newport v. Fact Concerts, Inc., 453 U.S. 247 (1981)",
        "note": (
            "Punitive damages are not available against a municipality or the State under §1983. "
            "To seek punitive damages, name individual officers in their individual capacity. "
            "Newport v. Fact Concerts, 453 U.S. 247 (1981)."
        ),
    }


def _injunctive_ex_parte_young() -> Dict[str, Any]:
    return {
        "type": "injunctive",
        "label": "Preliminary and permanent injunctive relief (Ex parte Young)",
        "amount_display": None,
        "legal_basis": "Ex parte Young, 209 U.S. 123 (1908)",
        "note": (
            "Injunctive relief against a state officer in official capacity is available under "
            "Ex parte Young to end an ongoing constitutional violation, notwithstanding the "
            "Eleventh Amendment. Specify the precise conduct to be enjoined."
        ),
    }


def _injunctive_equitable(basis: str = "Fed. R. Civ. P. 65 / equitable jurisdiction") -> Dict[str, Any]:
    return {
        "type": "injunctive",
        "label": "Preliminary and permanent injunctive relief",
        "amount_display": None,
        "legal_basis": basis,
        "note": (
            "Injunctive relief appropriate where ongoing harm is alleged and legal remedies are "
            "inadequate. Plead (1) likelihood of success on the merits, (2) irreparable harm, "
            "(3) balance of equities, and (4) public interest. Winter v. NRDC, 555 U.S. 7 (2008)."
        ),
    }


def _declaratory() -> Dict[str, Any]:
    return {
        "type": "declaratory",
        "label": "Declaratory relief",
        "amount_display": None,
        "legal_basis": "28 U.S.C. §2201 (Declaratory Judgment Act)",
        "note": "Declaration that Defendant's conduct violates Plaintiff's rights under applicable law.",
    }


def _record_correction(has_fcra: bool) -> Dict[str, Any]:
    return {
        "type": "record_correction",
        "label": "Correction of records and document production",
        "amount_display": None,
        "legal_basis": (
            "15 U.S.C. §1681i (FCRA dispute and correction right)"
            if has_fcra
            else "Equitable relief / Rule 26 discovery"
        ),
        "note": (
            "Plaintiff seeks: (1) correction of all inaccurate account records; "
            "(2) production of the complete account timeline and CP&I records; "
            "(3) all documentation relating to Plaintiff's account and the conduct alleged herein."
        ),
    }


def _attorney_fees(fee_bases: List[str]) -> Dict[str, Any]:
    return {
        "type": "attorney_fees",
        "label": "Reasonable attorney's fees",
        "amount_display": None,
        "legal_basis": "; ".join(fee_bases),
        "note": "Fee-shifting authorized by statute upon prevailing. Amount to be determined post-judgment.",
    }


def _costs(with_fees: bool = False) -> Dict[str, Any]:
    return {
        "type": "costs",
        "label": "Costs and disbursements of this action",
        "amount_display": None,
        "legal_basis": "Fed. R. Civ. P. 54(d)",
        "note": "" if with_fees else "Prevailing party may recover taxable costs.",
    }


def _further_relief() -> Dict[str, Any]:
    return {
        "type": "further_relief",
        "label": "Such other and further relief as this Court deems just and proper",
        "amount_display": None,
        "legal_basis": "",
        "note": "",
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_remedy_analysis(
    intake_state: Dict[str, Any],
    legal_results: Dict[str, Any],
    complaint_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a structured remedy list from intake facts and legal analysis output.
    Returns available relief items (rendered into the prayer section) and
    unavailable items (with Newport/immunity explanations).
    """
    if not isinstance(intake_state, dict):
        raise RemedyServiceError("intake_state must be a dictionary.")
    if not isinstance(legal_results, dict):
        raise RemedyServiceError("legal_results must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise RemedyServiceError("No complaints found in intake_state.")

    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise RemedyServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    text = _build_text(complaint)
    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    credit_impact = _safe_bool(complaint.get("creditImpactClaimed"))
    desired_outcome = (complaint.get("desiredOutcome", "") or "").lower()

    capacity = legal_results.get("capacity", {})
    target_type = capacity.get("target_type", "private")
    individual_defendants = capacity.get("capacity_split", {}).get("individual", [])
    ex_parte_young = capacity.get("ex_parte_young_available", False)

    # A government defendant is "entity-only" when no individual officer is named
    has_individual = bool(individual_defendants)
    is_municipal = legal_results.get("rights", {}).get("municipal_liability", False)

    has_1983 = _has_claim_type(legal_results, "§1983")
    has_fcra = _has_claim_type(legal_results, "FCRA")
    has_fdcpa = _has_claim_type(legal_results, "FDCPA")

    seeks_injunction = any(t in desired_outcome for t in [
        "stop", "injunction", "cease", "enjoin", "prevent",
        "policy", "restore", "reinstate", "return",
    ])
    seeks_record_correction = (
        credit_impact
        or has_fcra
        or any(t in text for t in [
            "record", "account", "cp&i", "correction", "inaccurate",
            "timeline", "alteration", "accurate", "correct",
        ])
    )
    has_ongoing = any(t in text for t in ["ongoing", "continue", "continuing", "still", "recurring"])

    available: List[Dict[str, Any]] = []
    unavailable: List[Dict[str, Any]] = []

    # --- Compensatory damages (always) ---
    available.append(_compensatory(financial_loss))

    # --- Punitive damages ---
    if target_type == "private":
        available.append(_punitive_private())
    elif has_individual:
        # Individual government officer named → Smith v. Wade allows punitive
        available.append(_punitive_individual(individual_defendants))
        if is_municipal:
            # Note the Newport bar against the entity alongside the individual award
            unavailable.append(_punitive_unavailable_note())
    else:
        # Government entity only (no named individual) → Newport bars punitive
        unavailable.append(_punitive_unavailable_note())

    # --- Injunctive relief ---
    if ex_parte_young:
        available.append(_injunctive_ex_parte_young())
    elif seeks_injunction or has_ongoing:
        basis = (
            "42 U.S.C. §1983; equitable jurisdiction"
            if has_1983
            else "Fed. R. Civ. P. 65 / equitable jurisdiction"
        )
        available.append(_injunctive_equitable(basis))

    # --- Declaratory relief (always) ---
    available.append(_declaratory())

    # --- Record correction / document production ---
    if seeks_record_correction:
        available.append(_record_correction(has_fcra))

    # --- Attorney's fees (only where legally authorized) ---
    fee_bases: List[str] = []
    if has_1983:
        fee_bases.append("42 U.S.C. §1988")
    if has_fcra:
        fee_bases.append("15 U.S.C. §1681n/o")
    if has_fdcpa:
        fee_bases.append("15 U.S.C. §1692k")

    if fee_bases:
        available.append(_attorney_fees(fee_bases))

    # --- Costs (always; separate from fees) ---
    available.append(_costs(with_fees=bool(fee_bases)))

    # --- Further relief (always) ---
    available.append(_further_relief())

    return {
        "complaintId": complaint.get("complaintId", ""),
        "target_type": target_type,
        "relief_items": available,
        "unavailable_relief": unavailable,
        "punitive_available": any(r["type"] == "punitive" for r in available),
        "injunctive_available": any(r["type"] == "injunctive" for r in available),
        "fees_authorized": bool(fee_bases),
        "fee_bases": fee_bases,
        "case_law": CASE_LAW,
        "note": (
            "Remedy analysis from intake facts and legal screening. "
            "Confirm availability of each item with counsel before filing."
        ),
    }
