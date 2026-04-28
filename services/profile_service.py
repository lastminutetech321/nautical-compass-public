from typing import Any, Dict


class ProfileServiceError(Exception):
    pass


def get_profile_summary(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ProfileServiceError("intake_state must be a dictionary.")

    identity = intake_state.get("identityProfile", {}) or {}
    business = intake_state.get("businessProfile", {}) or {}
    work = intake_state.get("workProfile", {}) or {}

    full_name = identity.get("fullLegalName", "")
    email = identity.get("email", "")
    phone = identity.get("phone", "")

    residential_address = identity.get("residentialAddress", {}) or {}
    city = residential_address.get("city", "")
    state = residential_address.get("state", "")

    business_name = business.get("businessName", "")
    entity_type = business.get("entityType", "none")
    operating_capacity = business.get("operatingCapacity", "individual")

    worker_type = work.get("workerType", "unknown")
    platforms_or_clients = work.get("platformsOrClients", []) or []
    weekly_hours_average = work.get("weeklyHoursAverage", 0)

    display_name = business_name if business_name else full_name

    return {
        "displayName": display_name,
        "fullLegalName": full_name,
        "email": email,
        "phone": phone,
        "location": {
            "city": city,
            "state": state,
        },
        "business": {
            "businessName": business_name,
            "entityType": entity_type,
            "operatingCapacity": operating_capacity,
        },
        "work": {
            "workerType": worker_type,
            "platformsOrClients": platforms_or_clients,
            "weeklyHoursAverage": weekly_hours_average,
        },
    }


def update_profile_basics(
    intake_state: Dict[str, Any],
    full_legal_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    business_name: str | None = None,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ProfileServiceError("intake_state must be a dictionary.")

    state = dict(intake_state)
    state.setdefault("identityProfile", {})
    state.setdefault("businessProfile", {})

    if full_legal_name is not None:
        state["identityProfile"]["fullLegalName"] = full_legal_name
    if email is not None:
        state["identityProfile"]["email"] = email
    if phone is not None:
        state["identityProfile"]["phone"] = phone
    if business_name is not None:
        state["businessProfile"]["businessName"] = business_name

    return state


if __name__ == "__main__":
    demo_state = {
        "identityProfile": {
            "fullLegalName": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-123-4567",
            "residentialAddress": {
                "city": "Baltimore",
                "state": "MD"
            }
        },
        "businessProfile": {
            "businessName": "Doe Services",
            "entityType": "none",
            "operatingCapacity": "individual"
        },
        "workProfile": {
            "workerType": "independent_contractor",
            "platformsOrClients": ["Uber", "AV"],
            "weeklyHoursAverage": 35
        }
    }

    summary = get_profile_summary(demo_state)
    print("displayName:", summary["displayName"])
    print("workerType:", summary["work"]["workerType"])
    print("location:", summary["location"])
