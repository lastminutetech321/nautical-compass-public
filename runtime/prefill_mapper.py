from typing import Any, Dict

from utils.spec_loader import load_spec


class PrefillMapperError(Exception):
    pass


def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if "[" in part and "]" in part:
            prefix = part[: part.index("[")]
            index_str = part[part.index("[") + 1 : part.index("]")]
            if prefix:
                if not isinstance(current, dict) or prefix not in current:
                    return None
                current = current[prefix]
            if not isinstance(current, list) or not index_str.isdigit():
                return None
            index = int(index_str)
            if index >= len(current):
                return None
            current = current[index]
            suffix = part[part.index("]") + 1 :]
            if suffix:
                if suffix.startswith("."):
                    suffix = suffix[1:]
                if suffix:
                    if not isinstance(current, dict) or suffix not in current:
                        return None
                    current = current[suffix]
        else:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
    return current


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def _resolve_source(source_path: str, intake_state: Dict[str, Any]) -> Any:
    return _get_nested_value(intake_state, source_path)


def _apply_field_map(field_map: Dict[str, Any], intake_state: Dict[str, Any]) -> Dict[str, Any]:
    mapped: Dict[str, Any] = {}

    for output_field, source_path in field_map.items():
        mapped[output_field] = _resolve_source(source_path, intake_state)

    return mapped


def _validate_required_fields(required_fields: list[str], intake_state: Dict[str, Any]) -> Dict[str, Any]:
    missing = []
    for field_path in required_fields:
        value = _resolve_source(field_path, intake_state)
        if _is_blank(value):
            missing.append(field_path)

    return {
        "valid": len(missing) == 0,
        "missingFields": missing,
    }


def map_document_fields(document_type: str, intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise PrefillMapperError("intake_state must be a dictionary.")

    spec = load_spec("prefill_mapping_spec")
    mappings = spec.get("prefillMappings", {})
    mapping = mappings.get(document_type)

    if mapping is None:
        valid = ", ".join(sorted(mappings.keys()))
        raise PrefillMapperError(f"Unknown document type '{document_type}'. Valid types: {valid}")

    required_fields = mapping.get("requiredFields", [])
    field_map = mapping.get("fieldMap", {})

    validation = _validate_required_fields(required_fields, intake_state)
    mapped_fields = _apply_field_map(field_map, intake_state)

    return {
        "documentType": document_type,
        "source": mapping.get("source"),
        "targetFile": mapping.get("targetFile"),
        "valid": validation["valid"],
        "missingFields": validation["missingFields"],
        "mappedFields": mapped_fields,
    }


if __name__ == "__main__":
    demo_state = load_spec("master_intake_schema")

    demo_state["identityProfile"]["fullLegalName"] = "Jane Doe"
    demo_state["identityProfile"]["email"] = "jane@example.com"
    demo_state["identityProfile"]["phone"] = "555-123-4567"
    demo_state["identityProfile"]["residentialAddress"]["street1"] = "123 Harbor Way"
    demo_state["identityProfile"]["residentialAddress"]["city"] = "Baltimore"
    demo_state["identityProfile"]["residentialAddress"]["state"] = "MD"
    demo_state["identityProfile"]["residentialAddress"]["postalCode"] = "21201"
    demo_state["businessProfile"]["businessName"] = "Doe Services"
    demo_state["businessProfile"]["entityType"] = "none"
    demo_state["businessProfile"]["einAvailable"] = False
    demo_state["workProfile"]["workerType"] = "independent_contractor"
    demo_state["workProfile"]["platformsOrClients"] = ["Uber", "AV"]
    demo_state["workProfile"]["setsOwnSchedule"] = True
    demo_state["workProfile"]["providesOwnTools"] = True
    demo_state["workProfile"]["weeklyHoursAverage"] = 35
    demo_state["incomeProfile"]["estimatedAnnualGrossIncome"] = 85000
    demo_state["documentProfile"]["invoiceReady"] = True

    for doc_type in ["w9", "invoice", "contractorProfile"]:
        result = map_document_fields(doc_type, demo_state)
        print(f"{doc_type}: valid={result['valid']}, missing={result['missingFields']}")
        print(result["mappedFields"])
