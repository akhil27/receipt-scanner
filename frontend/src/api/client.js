const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function handle(res) {
  if (res.status === 204) return null;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body && body.detail ? body.detail : `Request failed (${res.status})`;
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return body;
}

export function uploadReceipt(file, apiKey) {
  const form = new FormData();
  form.append("file", file);
  const headers = {};
  if (apiKey) headers["X-Api-Key"] = apiKey;
  return fetch(`${BASE}/receipts`, { method: "POST", body: form, headers }).then(handle);
}

export function getReceipts() {
  return fetch(`${BASE}/receipts`).then(handle);
}

export function getReceipt(id) {
  return fetch(`${BASE}/receipts/${id}`).then(handle);
}

export function updateReceipt(id, patch) {
  return fetch(`${BASE}/receipts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  }).then(handle);
}

export function deleteReceipt(id) {
  return fetch(`${BASE}/receipts/${id}`, { method: "DELETE" }).then(handle);
}

export function getSummary(start, end) {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const qs = params.toString();
  return fetch(`${BASE}/analytics/summary${qs ? `?${qs}` : ""}`).then(handle);
}
