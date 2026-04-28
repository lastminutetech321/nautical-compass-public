const API_BASE = "";

async function postJson(url, payload) {
  const response = await fetch(`${API_BASE}${url}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    throw new Error("Invalid JSON response");
  }

  if (!response.ok || data.ok === false) {
    throw new Error(data.error || data.detail || "Request failed");
  }

  return data.data;
}

export async function completeIntake(userId, intakeState) {
  return postJson("/api/intake/complete", {
    userId,
    intakeState
  });
}

export async function loadResultsSummary(intakeState) {
  return postJson("/api/results/summary", {
    intakeState
  });
}

export async function generateW9(userId, intakeState) {
  return postJson("/api/documents/generate-w9", {
    userId,
    intakeState
  });
}

export async function refreshHelmState(intakeState, scores = {}, routes = {}, history = []) {
  return postJson("/api/helm/state", {
    intakeState,
    scores,
    routes,
    history
  });
}

export { postJson };
