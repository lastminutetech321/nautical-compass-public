"""
Damages analysis service — Phase 3B.

Converts narrative harm allegations into categorized damages with estimated
ranges. Does not invent dollar amounts; inserts [FACT NEEDED] placeholders
where quantification is absent.

Categories:
  economic          — lost wages, unpaid invoices, out-of-pocket costs
  non_economic      — emotional distress, reputational harm, personal injury
  business_harm     — lost contracts, business interruption, lost opportunities
  service_account   — service cutoff, account correction, record-related harm
"""
from typing import Any, Dict, List, Optional


class DamagesServiceError(Exception):
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


def _analyze_economic(complaint: Dict[str, Any], text: str) -> Dict[str, Any]:
    financial_loss = _safe_number(complaint.get("financialLossAmount"))
    work_loss = _safe_number(complaint.get("workLossAmount"))

    items: List[Dict[str, Any]] = []

    if financial_loss > 0:
        items.append({
            "label": "Direct financial loss",
            "amount_stated": financial_loss,
            "amount_display": f"${financial_loss:,.2f}",
            "strength": "stated",
            "note": "Plaintiff-stated figure. Verify with invoices, bank records, or account statements.",
        })
    elif any(t in text for t in ["unpaid", "payment", "invoice", "refund", "fee", "charge", "bill"]):
        items.append({
            "label": "Unpaid amounts or disputed charges",
            "amount_stated": 0,
            "amount_display": _need("dollar amount — attach invoices, billing records, or account history"),
            "strength": "alleged_unquantified",
            "note": "Economic harm alleged but no dollar figure provided.",
        })

    if work_loss > 0:
        items.append({
            "label": "Lost income / work loss",
            "amount_stated": work_loss,
            "amount_display": f"${work_loss:,.2f}",
            "strength": "stated",
            "note": "Plaintiff-stated work loss. Verify with pay stubs, contracts, or work records.",
        })
    elif any(t in text for t in ["lost work", "work opportunity", "missed work", "could not work", "convention", "job", "gig", "shift"]):
        items.append({
            "label": "Lost work opportunities",
            "amount_stated": 0,
            "amount_display": _need("dollar amount — document specific jobs, rates, and dates of lost work"),
            "strength": "alleged_unquantified",
            "note": "Work-related loss alleged without quantification. Document each lost opportunity.",
        })

    strength = (
        "strong" if any(i["strength"] == "stated" for i in items)
        else "weak" if items
        else "none"
    )

    return {"category": "economic", "items": items, "strength": strength}


def _analyze_non_economic(complaint: Dict[str, Any], text: str) -> Dict[str, Any]:
    injury_claimed = _safe_bool(complaint.get("injuryClaimed"))
    emotional_stress = _safe_bool(complaint.get("emotionalStressClaimed"))
    credit_impact = _safe_bool(complaint.get("creditImpactClaimed"))

    items: List[Dict[str, Any]] = []

    if injury_claimed:
        items.append({
            "label": "Personal injury / physical harm",
            "amount_display": _need("medical bills, treatment records, or injury documentation"),
            "strength": "alleged",
            "note": "Personal injury claimed. Quantify with medical expenses and treatment records.",
        })

    if emotional_stress or any(t in text for t in ["stress", "anxiety", "distress", "trauma", "harm"]):
        items.append({
            "label": "Emotional distress",
            "amount_display": _need("documentation of distress — therapy records, impact statement, or medical evaluation"),
            "strength": "alleged_unquantified",
            "note": "Emotional distress must be more than speculative. Corroborate with records or testimony.",
        })

    if credit_impact or any(t in text for t in ["credit", "report", "score", "bureau", "reporting"]):
        items.append({
            "label": "Credit / reputational harm",
            "amount_display": _need("credit reports, denial letters, or evidence of adverse credit action"),
            "strength": "alleged_unquantified",
            "note": "Credit impact claimed. Obtain credit reports and document any denials or adverse actions.",
        })

    if any(t in text for t in ["reputation", "defam", "standing", "character"]):
        items.append({
            "label": "Reputational harm",
            "amount_display": _need("evidence of reputational impact — lost clients, public record, statements"),
            "strength": "alleged_unquantified",
            "note": "Reputational harm requires evidence of actual harm to standing or relationships.",
        })

    strength = "moderate" if items else "none"
    return {"category": "non_economic", "items": items, "strength": strength}


def _analyze_business_harm(complaint: Dict[str, Any], text: str) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []

    business_terms = [
        "business", "contract", "client", "customer", "lost opportunity",
        "convention", "event", "crew", "dispatch", "gear", "strike", "production",
        "freelance", "work order", "booking", "assignment",
    ]
    if any(t in text for t in business_terms):
        items.append({
            "label": "Business interruption / lost contracts",
            "amount_display": _need(
                "dollar amount — identify each lost contract or engagement with date, value, and link to defendant's conduct"
            ),
            "strength": "alleged_unquantified",
            "note": (
                "Business harm requires showing: (1) a specific business opportunity, "
                "(2) that was lost, (3) directly because of defendant's conduct. "
                "Document each lost engagement separately."
            ),
        })

    if any(t in text for t in ["communication", "phone", "number", "contact", "reachable", "unreachable"]):
        items.append({
            "label": "Communication failure / loss of phone number",
            "amount_display": _need(
                "dollar amount — quantify business impact of communication failure (missed jobs, lost contacts, re-routing costs)"
            ),
            "strength": "alleged_unquantified",
            "note": "Loss of phone number during active business operations is a quantifiable harm. Document job calendar.",
        })

    strength = "weak" if items else "none"
    return {"category": "business_harm", "items": items, "strength": strength}


def _analyze_service_account_harm(complaint: Dict[str, Any], text: str) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []

    if any(t in text for t in ["service", "cutoff", "cut off", "termination", "disconnected", "suspended"]):
        items.append({
            "label": "Service interruption / wrongful cutoff",
            "amount_display": _need(
                "dollar value of service period at issue — monthly plan cost × months affected, plus any reconnection fees"
            ),
            "strength": "alleged_unquantified",
            "note": "Document the plan rate, cutoff date, and restoration date to quantify service-loss damages.",
        })

    if any(t in text for t in ["record", "account", "timeline", "alteration", "inaccurate", "cp&i", "correction"]):
        items.append({
            "label": "Account record alteration / inaccurate records",
            "amount_display": _need(
                "cost of correction and any downstream harm — attach requested account timeline and CP&I records as exhibits"
            ),
            "strength": "alleged_unquantified",
            "note": (
                "Account record harm requires production of the CP&I records and account timeline "
                "to establish what the records show versus what actually occurred."
            ),
        })

    strength = "moderate" if items else "none"
    return {"category": "service_account", "items": items, "strength": strength}


def analyze_damages(
    intake_state: Dict[str, Any],
    complaint_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise DamagesServiceError("intake_state must be a dictionary.")

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        raise DamagesServiceError("No complaints found in intake_state.")

    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), None)
        if complaint is None:
            raise DamagesServiceError(f"Complaint not found: {complaint_id}")
    else:
        complaint = complaints[0]

    text = _build_text(complaint)
    financial_loss = _safe_number(complaint.get("financialLossAmount"))

    economic = _analyze_economic(complaint, text)
    non_economic = _analyze_non_economic(complaint, text)
    business = _analyze_business_harm(complaint, text)
    service = _analyze_service_account_harm(complaint, text)

    categories = [economic, non_economic, business, service]
    active = [c for c in categories if c["strength"] != "none"]

    total_stated = sum(
        i.get("amount_stated", 0)
        for c in categories
        for i in c.get("items", [])
        if isinstance(i.get("amount_stated"), (int, float))
    )

    damages_weak = financial_loss == 0 and total_stated == 0
    missing_amounts = [
        i["label"]
        for c in categories
        for i in c.get("items", [])
        if "[FACT NEEDED" in str(i.get("amount_display", ""))
    ]

    if total_stated > 0:
        overall_strength = "moderate"
    elif active:
        overall_strength = "weak"
    else:
        overall_strength = "none"

    return {
        "complaintId": complaint.get("complaintId", ""),
        "categories": {c["category"]: c for c in categories},
        "active_categories": [c["category"] for c in active],
        "total_stated_dollars": total_stated,
        "damages_weak": damages_weak,
        "missing_amounts": missing_amounts,
        "overall_strength": overall_strength,
        "note": (
            "Damages are categorized from intake narrative. Do not use these figures in filings "
            "without verification against actual records, receipts, and corroborating evidence."
        ),
    }
