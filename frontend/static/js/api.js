const Session = {
  get access() { return localStorage.getItem("mp_access") || ""; },
  get refresh() { return localStorage.getItem("mp_refresh") || ""; },
  get user() {
    try { return JSON.parse(localStorage.getItem("mp_user") || "null"); } catch { return null; }
  },
  get role() { return this.user ? this.user.role : null; },
  save(data) {
    localStorage.setItem("mp_access", data.access);
    localStorage.setItem("mp_refresh", data.refresh);
    localStorage.setItem("mp_user", JSON.stringify(data.user));
  },
  clear() {
    ["mp_access", "mp_refresh", "mp_user", "mp_cart_pharmacy"].forEach((k) => localStorage.removeItem(k));
  },
};

const API = (() => {
  const base = () => (localStorage.getItem("mp_api_base") || location.origin).replace(/\/$/, "");

  class ApiError extends Error {
    constructor(status, data) {
      super(messageFrom(status, data));
      this.status = status;
      this.data = data;
    }
  }

  function messageFrom(status, data) {
    if (!data) return `HTTP ${status}`;
    if (typeof data === "string") return data;
    if (data.detail) return typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    const parts = [];
    for (const [key, val] of Object.entries(data)) {
      const msg = Array.isArray(val) ? val.join("; ") : String(val);
      parts.push(key === "non_field_errors" ? msg : `${key}: ${msg}`);
    }
    return parts.join(" | ") || `HTTP ${status}`;
  }

  async function raw(path, { method = "GET", body = null, form = false, auth = true } = {}) {
    const headers = {};
    if (auth && Session.access) headers["Authorization"] = `Bearer ${Session.access}`;
    let payload;
    if (form) {
      payload = body;
    } else if (body !== null) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    let resp;
    try {
      resp = await fetch(base() + path, { method, headers, body: payload });
    } catch (e) {
      throw new ApiError(0, { detail: `Cannot reach server at ${base()} — is Django running?` });
    }
    let data = null;
    const text = await resp.text();
    if (text) {
      try { data = JSON.parse(text); } catch { data = text; }
    }
    if (!resp.ok) throw new ApiError(resp.status, data);
    return data;
  }

  async function request(path, opts = {}) {
    try {
      return await raw(path, opts);
    } catch (err) {
      if (err.status === 401 && Session.refresh && !path.startsWith("/auth/token/refresh")) {
        try {
          const tokens = await raw("/auth/token/refresh/", {
            method: "POST",
            body: { refresh: Session.refresh },
            auth: false,
          });
          localStorage.setItem("mp_access", tokens.access);
          if (tokens.refresh) localStorage.setItem("mp_refresh", tokens.refresh);
          return await raw(path, opts);
        } catch {
          Session.clear();
          location.hash = "#/auth";
          throw new ApiError(401, { detail: "Session expired — please log in again." });
        }
      }
      throw err;
    }
  }

  const get = (path) => request(path);
  const post = (path, body) => request(path, { method: "POST", body });
  const patch = (path, body) => request(path, { method: "PATCH", body });
  const put = (path, body) => request(path, { method: "PUT", body });
  const del = (path) => request(path, { method: "DELETE" });
  const upload = (path, formData) => request(path, { method: "POST", body: formData, form: true });

  const unwrap = (data) => (data && Array.isArray(data.results) ? data : { results: Array.isArray(data) ? data : [], count: data && data.count });

  return { ApiError, get, post, patch, put, del, upload, unwrap, base };
})();
