// frontend/js/API.js —— IIFE 版本（自動掛到 window.API）
(function () {
  // 後端 Base URL（建議在 index.html 先設 window.FINBOARD_API_BASE）
  const BASE_URL = (window.FINBOARD_API_BASE || "https://finboard-ol3p.onrender.com").replace(/\/+$/, "");

  // 統一管理 token 的 localStorage key（你之前有用過 fb_api_token / token，這裡都相容）
  const TOKEN_KEYS = ["fb_api_token", "API_TOKEN", "token"];

  // 讀/寫 Token（盡量與既有資料相容）
  function getToken() {
    for (const k of TOKEN_KEYS) {
      const v = localStorage.getItem(k);
      if (v) return v;
    }
    return "";
  }
  function setToken(tok) {
    const v = tok || "";
    // 主要寫入 fb_api_token，其它 key 也同步一份，確保舊碼能讀到
    localStorage.setItem("fb_api_token", v);
    localStorage.setItem("API_TOKEN", v);
    localStorage.setItem("token", v);
    // 若頁面上剛好有 token 欄位則同步 UI
    const el = document.querySelector("#token");
    if (el) el.value = v;
  }

  // ---- 共用：把 token 放進 header ----
  function authHeaders() {
    const tok = getToken();
    return tok ? { Authorization: "Bearer " + tok } : {};
  }

  // ---- 統一的 fetch 包裝：不拋錯，只回 {ok, data, httpStatus, error} ----
  async function fetchJSON(url, { method = "GET", headers = {}, body, params } = {}) {
    const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
    const fullUrl = url.startsWith("http") ? url : `${BASE_URL}${url}${qs}`;

    try {
      const res = await fetch(fullUrl, {
        method,
        headers: { "Content-Type": "application/json", ...authHeaders(), ...headers },
        body: body != null ? JSON.stringify(body) : undefined,
        // 開發時行為一致 & 避免快取
        mode: "cors",
        cache: "no-store",
        redirect: "follow",
      });

      const ctype = res.headers.get("content-type") || "";
      const isJSON = ctype.includes("application/json");
      const data = isJSON ? await res.json() : await res.text();

      if (!res.ok) {
        console.warn("⚠️ HTTP error", res.status, data);
        return { ok: false, httpStatus: res.status, data };
      }
      // 若後端把應用層錯誤放在 JSON（例如 code:403）
      if (data && (data.code === 403 || data.error === "forbidden")) {
        console.warn("⚠️ App error 403", data);
        return { ok: false, httpStatus: 200, data };
      }
      return { ok: true, data };
    } catch (err) {
      console.warn("⚠️ Network error", err);
      return { ok: false, error: err };
    }
  }

  // ---- 封裝常用 API（呼叫端請用 { ok, data } 判斷）----

  // 1) Auth echo（檢查 token 狀態）
  function echoAuth() {
    return fetchJSON("/api/auth/echo");
  }

  // 2) 價格（公開 / 不帶 token 也可）
  function getPrice(symbol) {
    return fetchJSON("/api/price", { params: { symbol } });
  }

  // 3) Watchlist
  function listWatchlist() {
    return fetchJSON("/api/watchlist");
  }
  function addWatchlist(symbol) {
    return fetchJSON("/api/watchlist", { method: "POST", body: { symbol } });
  }
  function deleteWatchlist(id) {
    return fetchJSON(`/api/watchlist/${id}`, { method: "DELETE" });
  }

  // 4) Alerts（需要 token）
  function listAlerts() {
    return fetchJSON("/api/alerts");
  }
  function patchAlert(id, data) {
    return fetchJSON(`/api/alerts/${id}`, { method: "PATCH", body: data });
  }

  // 導出到全域
  window.API = {
    BASE_URL,
    // token
    getToken, setToken, authHeaders,
    // 通用
    fetchJSON,
    // 具名 API
    echoAuth, getPrice,
    listWatchlist, addWatchlist, deleteWatchlist,
    listAlerts, patchAlert,
  };
})();
