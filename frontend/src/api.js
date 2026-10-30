const TOKEN_KEY = "thea_token";
const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function apiUrl(path) {
  if (!path) return path;
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path}`;
}

export function mediaUrl(path) {
  if (!path) return null;
  const token = getToken();
  if (!token) return apiUrl(path);
  const separator = path.includes("?") ? "&" : "?";
  return `${apiUrl(path)}${separator}token=${encodeURIComponent(token)}`;
}

export function wsUrl() {
  const token = getToken() || "";
  if (API_BASE) {
    const url = new URL(API_BASE, window.location.origin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = "/ws/alerts";
    url.search = `?token=${encodeURIComponent(token)}`;
    return url.toString();
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/alerts?token=${encodeURIComponent(token)}`;
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(apiUrl(path), { ...options, headers });
  if (response.status === 401) {
    clearToken();
    window.dispatchEvent(new Event("thea:unauthorized"));
    throw new ApiError("Your session expired. Please sign in again.", 401);
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      detail = response.statusText || detail;
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}
