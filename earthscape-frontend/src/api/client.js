// Thin fetch wrapper for the FastAPI backend (/api/v1).
// - Sends the httpOnly JWT cookie (credentials: "include").
// - Echoes the CSRF token cookie in X-CSRF-Token for state-changing calls (FR-1.5).
// - Normalises errors to the backend shape { error: { code, message } }.
const BASE = import.meta.env.VITE_API_BASE || "/api/v1";

function getCookie(name) {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function api(path, { method = "GET", body, params } = {}) {
  const url = new URL(BASE + path, window.location.origin);
  if (params) Object.entries(params).forEach(([k, v]) => v != null && v !== "" && url.searchParams.set(k, v));

  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const csrf = getCookie("csrf_token");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }

  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const e = data?.error;
    throw new ApiError(res.status, e?.code || "error", e?.message || res.statusText);
  }
  return data;
}
