import json
import sys

with open("agents/agent_registry.json", "r") as f:
    data = json.load(f)

required = [
    "agent_id",
    "agent_name",
    "agent_layer",
    "agent_type",
    "agent_status",
    "agent_permissions",
    "agent_dependencies",
    "agent_owner",
    "agent_version",
    "description"
]

ids = set()

for agent in data["agents"]:
    for field in required:
        if field not in agent:
            raise Exception(f"Missing field: {field}")

    if agent["agent_id"] in ids:
        raise Exception(f"Duplicate agent_id: {agent['agent_id']}")

    ids.add(agent["agent_id"])

    if not isinstance(agent["agent_permissions"], list):
        raise Exception(f"{agent['agent_id']} permissions must be list")

    if not isinstance(agent["agent_dependencies"], list):
        raise Exception(f"{agent['agent_id']} dependencies must be list")

print("VALIDATION PASSED")
print(f"Agents: {len(data['agents'])}")
