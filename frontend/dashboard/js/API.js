// frontend/js/API.js —— IIFE 版本（自動掛到 window.API）
(function () {
  // 後端 Base URL（建議在 index.html 先設 window.FINBOARD_API_BASE）
  const BASE_URL = (window.FINBOARD_API_BASE || "https://finboard-ol3p.onrender.com").replace(/\/+$/, "");

  // ----- Token 儲存 / 取得 -----
  function setToken(token) { localStorage.setItem("API_TOKEN", token || ""); }
  function getToken() { return localStorage.getItem("API_TOKEN") || ""; }
  function authHeaders() {
    const t = getToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
  }

  // ----- 統一的 fetch 包裝（自動帶 Authorization）-----
  async function fetchJSON(path, { method = "GET", params = null, body = null, headers = {} } = {}) {
    const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
    const url = `${BASE_URL}${path}${qs}`;
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", ...authHeaders(), ...headers }, // ★ 自動帶 Token
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let text = "";
      try { text = await res.text(); } catch (_) {}
      const err = new Error(`HTTP ${res.status} ${res.statusText}${text ? ` - ${text}` : ""}`);
      err.status = res.status; err.body = text;
      throw err;
    }
    return res.json();
  }

  // ----- 封裝 API -----
  // 讀取型（不需 Token）
  function getPrice(symbol) {
    return fetchJSON("/api/price", { params: { symbol } });
  }

  // 寫入/修改型（需要 Token；當 REQUIRE_TOKEN=1 時才會被強制）
  function patchAlert(id, data) {
    return fetchJSON(`/api/alerts/${id}`, { method: "PATCH", body: data });
  }

  // 導出到全域
  window.API = { setToken, getToken, authHeaders, fetchJSON, getPrice, patchAlert };
})();
