from typing import Any, Dict, List

from utils.spec_loader import load_spec


class RoutingError(Exception):
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


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _matches_rule(rule_when: Dict[str, Any], intake_state: Dict[str, Any], scores: Dict[str, Any]) -> bool:
    for key, expected in rule_when.items():
        if key.endswith("Min"):
            base_key = key[:-3]
            actual = _safe_int(scores.get(base_key))
            if actual < _safe_int(expected):
                return False

        elif key.endswith("Max"):
            base_key = key[:-3]
            actual = _safe_int(scores.get(base_key))
            if actual > _safe_int(expected):
                return False

        elif key == "entityTypeIn":
            actual = _get_nested_value(intake_state, "businessProfile.entityType")
            if actual not in expected:
                return False

        elif key == "workerTypeIn":
            actual = _get_nested_value(intake_state, "workProfile.workerType")
            if actual not in expected:
                return False

        elif key == "hasUnpaidInvoices":
            actual = _safe_bool(_get_nested_value(intake_state, "incomeProfile.hasUnpaidInvoices"))
            if actual != bool(expected):
                return False

        elif key == "hasComplaintOrDispute":
            actual = _safe_bool(_get_nested_value(intake_state, "complaintProfile.hasComplaintOrDispute"))
            if actual != bool(expected):
                return False

        else:
            raise RoutingError(f"Unsupported routing condition: {key}")

    return True


def compute_routes(intake_state: Dict[str, Any], scores: Dict[str, Any]) -> Dict[str, List[str] | Dict[str, str]]:
    if not isinstance(intake_state, dict):
        raise RoutingError("intake_state must be a dictionary.")
    if not isinstance(scores, dict):
        raise RoutingError("scores must be a dictionary.")

    spec = load_spec("upgrade_routing_spec")
    routing = spec.get("upgradeRouting", {})
    rules = routing.get("routingRules", [])
    blocked_rules = routing.get("blockedActionRules", [])
    one_click = routing.get("oneClickRoutes", {})

    recommended_modules: List[str] = []
    upgrade_paths: List[str] = []
    priority_actions: List[str] = []
    blocked_actions: List[str] = []

    for rule in rules:
        when = rule.get("when", {})
        if _matches_rule(when, intake_state, scores):
            for module in rule.get("recommend", []):
                if module not in recommended_modules:
                    recommended_modules.append(module)
                if module == "full_growth_package" and module not in upgrade_paths:
                    upgrade_paths.append(module)

            for action in rule.get("priorityActions", []):
                if action not in priority_actions:
                    priority_actions.append(action)

    for block_rule in blocked_rules:
        when = block_rule.get("when", {})
        if _matches_rule(when, intake_state, scores):
            for action in block_rule.get("block", []):
                if action not in blocked_actions:
                    blocked_actions.append(action)

    filtered_recommended = [m for m in recommended_modules if m not in blocked_actions]
    filtered_upgrade_paths = [m for m in upgrade_paths if m not in blocked_actions]

    filtered_one_click = {
        key: value for key, value in one_click.items() if key in filtered_recommended or key in filtered_upgrade_paths
    }

    return {
        "recommendedModules": filtered_recommended,
        "upgradePaths": filtered_upgrade_paths,
        "priorityActions": priority_actions,
        "blockedActions": blocked_actions,
        "oneClickRoutes": filtered_one_click,
    }


if __name__ == "__main__":
    demo_state = load_spec("master_intake_schema")

    demo_state["businessProfile"]["entityType"] = "none"
    demo_state["workProfile"]["workerType"] = "independent_contractor"
    demo_state["incomeProfile"]["hasUnpaidInvoices"] = True
    demo_state["complaintProfile"]["hasComplaintOrDispute"] = True

    demo_scores = {
        "classificationScore": 80,
        "savingsOpportunityScore": 93,
        "riskScore": 90,
        "complaintStrengthScore": 55,
        "documentReadinessScore": 60,
        "entityReadinessScore": 25,
        "overallPositionLabel": "high_exposure",
    }

    routes = compute_routes(demo_state, demo_scores)
    for key, value in routes.items():
        print(f"{key}: {value}")
