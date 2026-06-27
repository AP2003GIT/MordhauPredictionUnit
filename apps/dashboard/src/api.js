const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8002";
export const ALL_PLAYERS_LIMIT = 20000;

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

export function fetchPrediction() {
  return request("/predict/current");
}

export function fetchRatings(limit = ALL_PLAYERS_LIMIT) {
  return request(`/ratings?limit=${limit}`);
}

export function ingestHistory(limit = 9999) {
  return request(`/ingest/history?limit=${limit}`, { method: "POST" });
}
