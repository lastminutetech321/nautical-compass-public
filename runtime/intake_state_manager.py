import copy
from typing import Any, Dict, List

from utils.spec_loader import load_spec


class IntakeStateError(Exception):
    pass


def _deep_copy_schema() -> Dict[str, Any]:
    return copy.deepcopy(load_spec("master_intake_schema"))


def _parse_path(path: str) -> List[Any]:
    """
    Converts paths like:
    - identityProfile.fullLegalName
    - complaintProfile.complaints[0].targetName
    into token lists.
    """
    if not path or not isinstance(path, str):
        raise IntakeStateError("Field path must be a non-empty string.")

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
                raise IntakeStateError(f"Invalid list index in path: {path}")

            tokens.append(int(index_str))
            part = suffix

        if part:
            tokens.append(part)

    return tokens


def _ensure_list_size(target: List[Any], index: int) -> None:
    while len(target) <= index:
        target.append({})


def _set_nested_value(obj: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    tokens = _parse_path(path)
    current: Any = obj

    for i, token in enumerate(tokens[:-1]):
        next_token = tokens[i + 1]

        if isinstance(token, str):
            if token not in current or current[token] is None:
                current[token] = [] if isinstance(next_token, int) else {}

            current = current[token]

        elif isinstance(token, int):
            if not isinstance(current, list):
                raise IntakeStateError(f"Expected list while setting path: {path}")

            _ensure_list_size(current, token)
            if current[token] is None:
                current[token] = [] if isinstance(next_token, int) else {}

            current = current[token]

        else:
            raise IntakeStateError(f"Unsupported token in path: {token}")

    final_token = tokens[-1]

    if isinstance(final_token, str):
        current[final_token] = value
    elif isinstance(final_token, int):
        if not isinstance(current, list):
            raise IntakeStateError(f"Expected list at final path token: {path}")
        _ensure_list_size(current, final_token)
        current[final_token] = value
    else:
        raise IntakeStateError(f"Unsupported final token in path: {final_token}")

    return obj


def get_intake_state(user_id: str) -> Dict[str, Any]:
    """
    Phase 1 in-memory state only.
    Returns a fresh schema object.
    """
    if not user_id:
        raise IntakeStateError("user_id is required.")
    return _deep_copy_schema()


def update_intake_field(user_id: str, field_path: str, value: Any, intake_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Updates a single field path in the intake state and returns updated state.
    """
    if not user_id:
        raise IntakeStateError("user_id is required.")

    state = copy.deepcopy(intake_state) if intake_state is not None else _deep_copy_schema()
    updated_state = _set_nested_value(state, field_path, value)

    updated_state["updatedAt"] = "runtime_update"
    return updated_state


def save_intake_section(user_id: str, section_id: str, payload: Dict[str, Any], intake_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Saves a batch of field_path:value pairs for one section.
    """
    if not user_id:
        raise IntakeStateError("user_id is required.")
    if not section_id:
        raise IntakeStateError("section_id is required.")
    if not isinstance(payload, dict):
        raise IntakeStateError("payload must be a dictionary of field paths to values.")

    state = copy.deepcopy(intake_state) if intake_state is not None else _deep_copy_schema()

    for field_path, value in payload.items():
        _set_nested_value(state, field_path, value)

    state["updatedAt"] = "section_save"
    if state.get("status") == "draft":
        state["status"] = "in_progress"

    history = state.setdefault("history", [])
    history.append(
        {
            "eventType": "section_saved",
            "section": section_id,
            "timestamp": "runtime_event",
            "actor": user_id,
        }
    )
    return state


def mark_intake_complete(user_id: str, intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not user_id:
        raise IntakeStateError("user_id is required.")
    if not isinstance(intake_state, dict):
        raise IntakeStateError("intake_state must be a dictionary.")

    state = copy.deepcopy(intake_state)
    state["status"] = "complete"
    state["completionPercent"] = 100
    state["updatedAt"] = "intake_complete"

    history = state.setdefault("history", [])
    history.append(
        {
            "eventType": "intake_completed",
            "section": "all",
            "timestamp": "runtime_event",
            "actor": user_id,
        }
    )
    return state


if __name__ == "__main__":
    demo_user = "demo-user"

    state = get_intake_state(demo_user)
    state = update_intake_field(demo_user, "identityProfile.fullLegalName", "Jane Doe", state)
    state = update_intake_field(demo_user, "identityProfile.email", "jane@example.com", state)
    state = save_intake_section(
        demo_user,
        "identity",
        {
            "identityProfile.firstName": "Jane",
            "identityProfile.lastName": "Doe",
            "businessProfile.businessName": "Doe Services",
        },
        state,
    )
    state = mark_intake_complete(demo_user, state)

    print("status:", state["status"])
    print("name:", state["identityProfile"]["fullLegalName"])
    print("business:", state["businessProfile"]["businessName"])
    print("history_count:", len(state.get("history", [])))
