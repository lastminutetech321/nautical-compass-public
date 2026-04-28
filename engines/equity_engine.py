from typing import Any, Dict


class EquityEngineError(Exception):
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


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def analyze_equity_position(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise EquityEngineError("intake_state must be a dictionary.")

    income = intake_state.get("incomeProfile", {}) or {}
    expenses = intake_state.get("expenseProfile", {}) or {}
    business = intake_state.get("businessProfile", {}) or {}
    compliance = intake_state.get("complianceProfile", {}) or {}

    gross_income = _safe_number(income.get("estimatedAnnualGrossIncome"))
    net_income = _safe_number(income.get("estimatedAnnualNetIncome"))
    annual_expenses = _safe_number(expenses.get("estimatedAnnualBusinessExpenses"))
    tracks_mileage = _safe_bool(expenses.get("tracksMileage"))
    unpaid_invoices = _safe_bool(income.get("hasUnpaidInvoices"))
    separate_bank = _safe_bool(business.get("separateBusinessBankAccount"))
    entity_type = business.get("entityType", "none")
    uses_contracts = _safe_bool(compliance.get("usesWrittenContracts"))
    has_insurance = _safe_bool(compliance.get("hasInsurance"))
    recordkeeping = compliance.get("recordkeepingStrength", "weak")

    deduction_opportunity = 0
    if gross_income > 0 and annual_expenses == 0:
        deduction_opportunity += 25
    elif annual_expenses > 0:
        deduction_opportunity += 10

    if not tracks_mileage:
        deduction_opportunity += 15

    if recordkeeping == "weak":
        deduction_opportunity += 20
    elif recordkeeping == "moderate":
        deduction_opportunity += 10

    structure_opportunity = 0
    if entity_type in (None, "", "none"):
        structure_opportunity += 30
    if not separate_bank:
        structure_opportunity += 15
    if not uses_contracts:
        structure_opportunity += 10
    if not has_insurance:
        structure_opportunity += 10

    income_leverage = 0
    if gross_income >= 100000:
        income_leverage += 30
    elif gross_income >= 70000:
        income_leverage += 22
    elif gross_income >= 40000:
        income_leverage += 15
    elif gross_income > 0:
        income_leverage += 8

    if net_income > 0:
        income_leverage += 10

    receivable_pressure = 15 if unpaid_invoices else 0

    savings_opportunity_score = _clamp_score(
        deduction_opportunity + structure_opportunity + income_leverage + receivable_pressure
    )

    equity_leak_points = []
    if annual_expenses == 0 and gross_income > 0:
        equity_leak_points.append("No documented business expenses captured.")
    if not tracks_mileage:
        equity_leak_points.append("Mileage tracking not enabled.")
    if entity_type in (None, "", "none"):
        equity_leak_points.append("No business entity separation in place.")
    if not separate_bank:
        equity_leak_points.append("No separate business bank account.")
    if unpaid_invoices:
        equity_leak_points.append("Unpaid invoices or uncollected revenue detected.")
    if not uses_contracts:
        equity_leak_points.append("Written contracts not consistently used.")
    if not has_insurance:
        equity_leak_points.append("Insurance protection not in place.")

    if gross_income >= 70000 and entity_type in (None, "", "none"):
        recommended_structure = "review_llc_or_s_corp"
    elif gross_income >= 40000 and entity_type in (None, "", "none"):
        recommended_structure = "review_llc"
    else:
        recommended_structure = "optimize_current_structure"

    if gross_income >= 100000:
        positioning_band = "high_leverage"
    elif gross_income >= 70000:
        positioning_band = "growth_ready"
    elif gross_income >= 40000:
        positioning_band = "developing"
    elif gross_income > 0:
        positioning_band = "early_stage"
    else:
        positioning_band = "unknown"

    return {
        "equitySnapshot": {
            "grossIncome": gross_income,
            "netIncome": net_income,
            "annualExpenses": annual_expenses,
            "entityType": entity_type,
            "recordkeepingStrength": recordkeeping,
        },
        "scores": {
            "savingsOpportunityScore": savings_opportunity_score,
            "deductionOpportunityScore": _clamp_score(deduction_opportunity),
            "structureOpportunityScore": _clamp_score(structure_opportunity),
            "incomeLeverageScore": _clamp_score(income_leverage),
            "receivablePressureScore": _clamp_score(receivable_pressure),
        },
        "positioningBand": positioning_band,
        "recommendedStructure": recommended_structure,
        "equityLeakPoints": equity_leak_points,
        "priorityActions": _build_priority_actions(
            tracks_mileage=tracks_mileage,
            annual_expenses=annual_expenses,
            entity_type=entity_type,
            separate_bank=separate_bank,
            unpaid_invoices=unpaid_invoices,
            uses_contracts=uses_contracts,
        ),
    }


def _build_priority_actions(
    *,
    tracks_mileage: bool,
    annual_expenses: float,
    entity_type: str,
    separate_bank: bool,
    unpaid_invoices: bool,
    uses_contracts: bool,
) -> list[str]:
    actions: list[str] = []

    if annual_expenses == 0:
        actions.append("capture_business_expenses")
    if not tracks_mileage:
        actions.append("enable_mileage_tracking")
    if entity_type in (None, "", "none"):
        actions.append("review_entity_structure")
    if not separate_bank:
        actions.append("open_separate_business_account")
    if unpaid_invoices:
        actions.append("collect_outstanding_revenue")
    if not uses_contracts:
        actions.append("activate_contract_workflow")

    return actions


if __name__ == "__main__":
    demo_state = {
        "incomeProfile": {
            "estimatedAnnualGrossIncome": 85000,
            "estimatedAnnualNetIncome": 65000,
            "hasUnpaidInvoices": True,
        },
        "expenseProfile": {
            "estimatedAnnualBusinessExpenses": 0,
            "tracksMileage": False,
        },
        "businessProfile": {
            "entityType": "none",
            "separateBusinessBankAccount": False,
        },
        "complianceProfile": {
            "usesWrittenContracts": False,
            "hasInsurance": False,
            "recordkeepingStrength": "weak",
        },
    }

    result = analyze_equity_position(demo_state)
    print("positioningBand:", result["positioningBand"])
    print("recommendedStructure:", result["recommendedStructure"])
    print("savingsOpportunityScore:", result["scores"]["savingsOpportunityScore"])
    print("equityLeakPoints:", result["equityLeakPoints"])
    print("priorityActions:", result["priorityActions"])
