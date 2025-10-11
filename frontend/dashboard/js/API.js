const BASE_URL = import.meta?.env?.VITE_API_BASE_URL || process.env.API_BASE_URL || "";

async function fetchJSON(path, { method="GET", params={}, headers={}, body } = {}) {
  const qs = new URLSearchParams(params).toString();
  const url = `${BASE_URL}${path}${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function getPrice(symbol) {
  return fetchJSON("/api/price", { params: { symbol } });
}

// 預留授權機制（第4階段會用到）
export function setToken(t){ localStorage.setItem("API_TOKEN", t); }
export function authHeaders(){
  const t = localStorage.getItem("API_TOKEN");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export default { getPrice, setToken, authHeaders };
