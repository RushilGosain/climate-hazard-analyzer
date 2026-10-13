const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

async function get(path, params = {}) {
  const res = await fetch(`${BASE}${path}?${new URLSearchParams(params)}`);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
}

export const getMeta = () => get("/api/meta");
export const geocode = (q) => get("/api/geocode", { q });
export const analyze = (hazard, params) => get(`/api/hazards/${hazard}`, params);
export const csvUrl = (hazard, params) => `${BASE}/api/hazards/${hazard}/export.csv?${new URLSearchParams(params)}`;
