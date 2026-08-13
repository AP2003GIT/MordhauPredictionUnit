const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8002";
const DATA_API_BASE_URL =
  import.meta.env.VITE_DATA_API_BASE_URL || "http://localhost:8001";
const AUTOBALANCE_API_BASE_URL =
  import.meta.env.VITE_AUTOBALANCE_API_BASE_URL || "http://localhost:8003";
export const ALL_PLAYERS_LIMIT = 20000;

async function requestFrom(baseUrl, path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail || `${response.status} ${response.statusText}`);
  }
  return payload;
}

async function request(path, options = {}) {
  return requestFrom(API_BASE_URL, path, options);
}

export function fetchPrediction() {
  return request("/predict/current");
}

export function fetchRandomPrediction(teamSize = 5) {
  return request(`/predict/random?team_size=${teamSize}`);
}

export function fetchModelStatus() {
  return request("/model/status");
}

export function fetchSyncStatus() {
  return requestFrom(DATA_API_BASE_URL, "/stats/sync");
}

export function trainModel() {
  return request("/model/train", { method: "POST" });
}

export function fetchRatings(limit = ALL_PLAYERS_LIMIT) {
  return request(`/ratings?limit=${limit}`);
}

export function ingestHistory(limit = 9999) {
  return request(`/ingest/history?limit=${limit}`, { method: "POST" });
}

export function fetchBalancePreview(options = {}) {
  return requestFrom(AUTOBALANCE_API_BASE_URL, "/balance/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });
}
