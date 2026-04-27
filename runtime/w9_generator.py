from typing import Any, Dict

from utils.spec_loader import load_spec
from runtime.prefill_mapper import map_document_fields


class W9GeneratorError(Exception):
    pass


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _resolve_tax_classification(entity_type: Any, generator_spec: Dict[str, Any]) -> str:
    config = generator_spec.get("fieldResolution", {}).get("federalTaxClassification", {})
    mapping = config.get("map", {})
    fallback = config.get("fallback", "individual_sole_proprietor")

    if entity_type in mapping:
        return mapping[entity_type]
    return fallback


def _resolve_tin_type(ein_available: Any, generator_spec: Dict[str, Any]) -> str:
    config = generator_spec.get("fieldResolution", {}).get("tinType", {})
    mapping = config.get("map", {})
    fallback = config.get("fallback", "ssn_or_individual_tin")

    key = "true" if bool(ein_available) else "false"
    return mapping.get(key, fallback)


def generate_w9_payload(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise W9GeneratorError("intake_state must be a dictionary.")

    generator_spec = load_spec("w9_generator_spec")
    mapped = map_document_fields("w9", intake_state)

    if not mapped.get("valid", False):
        return {
            "documentType": "w9",
            "status": "blocked",
            "reviewRequired": True,
            "valid": False,
            "missingFields": mapped.get("missingFields", []),
            "payload": {},
            "message": "Missing required intake fields",
        }

    fields = mapped.get("mappedFields", {})

    name_line = fields.get("name")
    business_name_line = fields.get("businessName")
    entity_type = fields.get("taxClassification")
    address_line1 = fields.get("addressLine1")
    city = fields.get("city")
    state = fields.get("state")
    zip_code = fields.get("zip")
    ein_available = fields.get("einAvailable")

    payload = {
        "nameLine": name_line or "",
        "businessNameLine": business_name_line or "",
        "federalTaxClassification": _resolve_tax_classification(entity_type, generator_spec),
        "addressLine1": address_line1 or "",
        "city": city or "",
        "state": state or "",
        "zip": zip_code or "",
        "tinType": _resolve_tin_type(ein_available, generator_spec),
        "tinValue": "",
    }

    validation_rules = generator_spec.get("validationRules", [])
    validation_errors = []

    for rule in validation_rules:
        field_path = rule.get("field", "")
        if not field_path.startswith("payload."):
            continue
        payload_key = field_path.replace("payload.", "", 1)
        if rule.get("type") == "required" and _is_blank(payload.get(payload_key)):
            validation_errors.append(payload_key)

    valid = len(validation_errors) == 0

    return {
        "documentType": "w9",
        "status": "prefilled" if valid else "blocked",
        "reviewRequired": True,
        "valid": valid,
        "missingFields": validation_errors,
        "payload": payload,
        "message": "W-9 payload ready for review" if valid else "Missing required intake fields",
    }


def build_w9_review_state(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    result = generate_w9_payload(intake_state)

    return {
        "documentType": "w9",
        "reviewRequired": True,
        "valid": result["valid"],
        "status": result["status"],
        "message": result["message"],
        "payload": result["payload"],
        "missingFields": result.get("missingFields", []),
        "actions": {
            "primaryButton": "Generate W-9",
            "successState": "W-9 payload ready for review",
            "failureState": "Missing required intake fields",
        },
    }


if __name__ == "__main__":
    demo_state = load_spec("master_intake_schema")

    demo_state["identityProfile"]["fullLegalName"] = "Jane Doe"
    demo_state["identityProfile"]["residentialAddress"]["street1"] = "123 Harbor Way"
    demo_state["identityProfile"]["residentialAddress"]["city"] = "Baltimore"
    demo_state["identityProfile"]["residentialAddress"]["state"] = "MD"
    demo_state["identityProfile"]["residentialAddress"]["postalCode"] = "21201"
    demo_state["businessProfile"]["businessName"] = "Doe Services"
    demo_state["businessProfile"]["entityType"] = "none"
    demo_state["businessProfile"]["einAvailable"] = False

    result = build_w9_review_state(demo_state)
    print("valid:", result["valid"])
    print("status:", result["status"])
    print("message:", result["message"])
    print("payload:", result["payload"])
