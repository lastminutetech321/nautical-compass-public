from typing import Any, Dict


class BusinessServiceError(Exception):
    pass


def get_business_summary(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise BusinessServiceError("intake_state must be a dictionary.")

    business = intake_state.get("businessProfile", {}) or {}
    compliance = intake_state.get("complianceProfile", {}) or {}

    return {
        "businessName": business.get("businessName", ""),
        "operatingCapacity": business.get("operatingCapacity", "individual"),
        "entityType": business.get("entityType", "none"),
        "einAvailable": business.get("einAvailable", False),
        "separateBusinessBankAccount": business.get("separateBusinessBankAccount", False),
        "usesWrittenContracts": compliance.get("usesWrittenContracts", False),
        "hasInsurance": compliance.get("hasInsurance", False),
        "recordkeepingStrength": compliance.get("recordkeepingStrength", "weak"),
    }


def update_business_profile(
    intake_state: Dict[str, Any],
    business_name: str | None = None,
    operating_capacity: str | None = None,
    entity_type: str | None = None,
    ein_available: bool | None = None,
    separate_business_bank_account: bool | None = None,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise BusinessServiceError("intake_state must be a dictionary.")

    state = dict(intake_state)
    state.setdefault("businessProfile", {})

    if business_name is not None:
        state["businessProfile"]["businessName"] = business_name
    if operating_capacity is not None:
        state["businessProfile"]["operatingCapacity"] = operating_capacity
    if entity_type is not None:
        state["businessProfile"]["entityType"] = entity_type
    if ein_available is not None:
        state["businessProfile"]["einAvailable"] = ein_available
    if separate_business_bank_account is not None:
        state["businessProfile"]["separateBusinessBankAccount"] = separate_business_bank_account

    return state


def update_business_compliance(
    intake_state: Dict[str, Any],
    uses_written_contracts: bool | None = None,
    has_insurance: bool | None = None,
    recordkeeping_strength: str | None = None,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise BusinessServiceError("intake_state must be a dictionary.")

    state = dict(intake_state)
    state.setdefault("complianceProfile", {})

    if uses_written_contracts is not None:
        state["complianceProfile"]["usesWrittenContracts"] = uses_written_contracts
    if has_insurance is not None:
        state["complianceProfile"]["hasInsurance"] = has_insurance
    if recordkeeping_strength is not None:
        state["complianceProfile"]["recordkeepingStrength"] = recordkeeping_strength

    return state


if __name__ == "__main__":
    demo_state = {
        "businessProfile": {
            "businessName": "Doe Services",
            "operatingCapacity": "individual",
            "entityType": "none",
            "einAvailable": False,
            "separateBusinessBankAccount": False,
        },
        "complianceProfile": {
            "usesWrittenContracts": False,
            "hasInsurance": False,
            "recordkeepingStrength": "weak",
        },
    }

    summary = get_business_summary(demo_state)
    print("businessName:", summary["businessName"])
    print("entityType:", summary["entityType"])
    print("hasInsurance:", summary["hasInsurance"])
