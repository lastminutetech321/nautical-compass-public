from typing import Any, Dict


class IncomeServiceError(Exception):
    pass


def get_income_summary(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise IncomeServiceError("intake_state must be a dictionary.")

    income = intake_state.get("incomeProfile", {}) or {}

    gross_income = income.get("estimatedAnnualGrossIncome", 0)
    net_income = income.get("estimatedAnnualNetIncome", 0)
    unpaid_invoices = income.get("hasUnpaidInvoices", False)

    return {
        "receivesW2": income.get("receivesW2", False),
        "receives1099": income.get("receives1099", False),
        "estimatedAnnualGrossIncome": gross_income,
        "estimatedAnnualNetIncome": net_income,
        "hasUnpaidInvoices": unpaid_invoices,
        "estimatedIncomeBand": _get_income_band(gross_income),
    }


def update_income_profile(
    intake_state: Dict[str, Any],
    receives_w2: bool | None = None,
    receives_1099: bool | None = None,
    estimated_annual_gross_income: float | int | None = None,
    estimated_annual_net_income: float | int | None = None,
    has_unpaid_invoices: bool | None = None,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise IncomeServiceError("intake_state must be a dictionary.")

    state = dict(intake_state)
    state.setdefault("incomeProfile", {})

    if receives_w2 is not None:
        state["incomeProfile"]["receivesW2"] = receives_w2
    if receives_1099 is not None:
        state["incomeProfile"]["receives1099"] = receives_1099
    if estimated_annual_gross_income is not None:
        state["incomeProfile"]["estimatedAnnualGrossIncome"] = estimated_annual_gross_income
    if estimated_annual_net_income is not None:
        state["incomeProfile"]["estimatedAnnualNetIncome"] = estimated_annual_net_income
    if has_unpaid_invoices is not None:
        state["incomeProfile"]["hasUnpaidInvoices"] = has_unpaid_invoices

    return state


def _get_income_band(gross_income: Any) -> str:
    try:
        value = float(gross_income)
    except (TypeError, ValueError):
        return "unknown"

    if value >= 100000:
        return "100k_plus"
    if value >= 70000:
        return "70k_to_99k"
    if value >= 40000:
        return "40k_to_69k"
    if value > 0:
        return "under_40k"
    return "unknown"


if __name__ == "__main__":
    demo_state = {
        "incomeProfile": {
            "receivesW2": False,
            "receives1099": True,
            "estimatedAnnualGrossIncome": 85000,
            "estimatedAnnualNetIncome": 65000,
            "hasUnpaidInvoices": True,
        }
    }

    summary = get_income_summary(demo_state)
    print("receives1099:", summary["receives1099"])
    print("estimatedAnnualGrossIncome:", summary["estimatedAnnualGrossIncome"])
    print("estimatedIncomeBand:", summary["estimatedIncomeBand"])
