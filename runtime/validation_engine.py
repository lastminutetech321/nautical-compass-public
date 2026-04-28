from typing import Any, Dict, List, Tuple

from utils.spec_loader import load_spec


class ValidationError(Exception):
    pass


REQUIRED_SECTIONS = {
    "identity": [
        "identityProfile.fullLegalName",
        "identityProfile.firstName",
        "identityProfile.lastName",
        "identityProfile.email",
        "identityProfile.phone",
    ],
    "address": [
        "identityProfile.residentialAddress.street1",
        "identityProfile.residentialAddress.city",
        "identityProfile.residentialAddress.state",
        "identityProfile.residentialAddress.postalCode",
    ],
    "work": [
        "workProfile.workerType",
    ],
    "income": [
        "incomeProfile.estimatedAnnualGrossIncome",
    ],
}


def _parse_path(path: str) -> List[Any]:
    if not path or not isinstance(path, str):
        raise ValidationError("Field path must be a non-empty string.")

    tokens: List[Any] = []
    parts = path.split(".")

    for part in parts:
        while "[" in part and "]" in part:
            prefix = part[: part.index("[")]
            index_str = part[part.index("[") + 1 : part.index("]")]
            suffix = part[part.index("]") + 1 :]

            if prefix:
                tokens.append(prefix)

            if not index_str.isdigit():
                raise ValidationError(f"Invalid list index in path: {path}")

            tokens.append(int(index_str))
            part = suffix

        if part:
            tokens.append(part)

    return tokens


def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
    tokens = _parse_path(path)
    current: Any = data

    for token in tokens:
        if isinstance(token, str):
            if not isinstance(current, dict) or token not in current:
                return None
            current = current[token]
        elif isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return None
            current = current[token]
        else:
            return None

    return current


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def validate_field(field_path: str, value: Any) -> List[str]:
    errors: List[str] = []

    if not field_path:
        return ["Field path is required."]

    if field_path.endswith("email"):
        if _is_blank(value):
            errors.append("Email is required.")
        elif "@" not in str(value):
            errors.append("Email must contain @.")

    elif field_path.endswith("phone"):
        if _is_blank(value):
            errors.append("Phone is required.")

    elif field_path.endswith("dateOfBirth"):
        if _is_blank(value):
            errors.append("Date of birth is required.")

    elif field_path.endswith("estimatedAnnualGrossIncome"):
        if value is None or value == "":
            errors.append("Estimated annual gross income is required.")
        else:
            try:
                if float(value) < 0:
                    errors.append("Estimated annual gross income cannot be negative.")
            except (TypeError, ValueError):
                errors.append("Estimated annual gross income must be numeric.")

    elif field_path.endswith("estimatedAnnualNetIncome") or field_path.endswith("estimatedAnnualBusinessExpenses"):
        if value not in (None, ""):
            try:
                if float(value) < 0:
                    errors.append(f"{field_path} cannot be negative.")
            except (TypeError, ValueError):
                errors.append(f"{field_path} must be numeric.")

    else:
        if any(
            field_path.endswith(suffix)
            for suffix in ["fullLegalName", "firstName", "lastName", "street1", "city", "state", "postalCode", "workerType"]
        ):
            if _is_blank(value):
                errors.append(f"{field_path} is required.")

    return errors


def validate_section(section_id: str, intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not section_id:
        raise ValidationError("section_id is required.")
    if not isinstance(intake_state, dict):
        raise ValidationError("intake_state must be a dictionary.")

    required_fields = REQUIRED_SECTIONS.get(section_id, [])
    field_errors: Dict[str, List[str]] = {}

    for field_path in required_fields:
        value = _get_nested_value(intake_state, field_path)
        errors = validate_field(field_path, value)
        if errors:
            field_errors[field_path] = errors

    return {
        "sectionId": section_id,
        "valid": len(field_errors) == 0,
        "errors": field_errors,
    }


def validate_w9_requirements(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ValidationError("intake_state must be a dictionary.")

    w9_spec = load_spec("w9_generator_spec")
    required_fields = w9_spec.get("requirements", {}).get("requiredFields", [])
    missing_fields: List[str] = []
    field_errors: Dict[str, List[str]] = {}

    for field_path in required_fields:
        value = _get_nested_value(intake_state, field_path)
        errors = validate_field(field_path, value)

        if _is_blank(value):
            missing_fields.append(field_path)

        if errors:
            field_errors[field_path] = errors

    return {
        "valid": len(missing_fields) == 0 and len(field_errors) == 0,
        "missingFields": missing_fields,
        "errors": field_errors,
    }


def validate_intake_minimum(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    results = {}
    overall_valid = True

    for section_id in REQUIRED_SECTIONS:
        section_result = validate_section(section_id, intake_state)
        results[section_id] = section_result
        if not section_result["valid"]:
            overall_valid = False

    return {
        "valid": overall_valid,
        "sections": results,
    }


if __name__ == "__main__":
    demo_state = load_spec("master_intake_schema")

    demo_state["identityProfile"]["fullLegalName"] = "Jane Doe"
    demo_state["identityProfile"]["firstName"] = "Jane"
    demo_state["identityProfile"]["lastName"] = "Doe"
    demo_state["identityProfile"]["email"] = "jane@example.com"
    demo_state["identityProfile"]["phone"] = "555-123-4567"
    demo_state["identityProfile"]["residentialAddress"]["street1"] = "123 Harbor Way"
    demo_state["identityProfile"]["residentialAddress"]["city"] = "Baltimore"
    demo_state["identityProfile"]["residentialAddress"]["state"] = "MD"
    demo_state["identityProfile"]["residentialAddress"]["postalCode"] = "21201"
    demo_state["workProfile"]["workerType"] = "independent_contractor"
    demo_state["incomeProfile"]["estimatedAnnualGrossIncome"] = 85000

    print("identity:", validate_section("identity", demo_state)["valid"])
    print("address:", validate_section("address", demo_state)["valid"])
    print("work:", validate_section("work", demo_state)["valid"])
    print("income:", validate_section("income", demo_state)["valid"])
    print("w9:", validate_w9_requirements(demo_state)["valid"])
