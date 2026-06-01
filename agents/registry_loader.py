import json

REGISTRY_PATH = "agents/agent_registry.json"

def load_registry():
    with open(REGISTRY_PATH, "r") as f:
        return json.load(f)

def get_agents():
    return load_registry()["agents"]

def get_agent(agent_id):
    for agent in get_agents():
        if agent["agent_id"] == agent_id:
            return agent
    return None

if __name__ == "__main__":
    agents = get_agents()
    print(f"Loaded {len(agents)} agents")
