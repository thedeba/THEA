export const REFRESH_KEY = "thea_dashboard_refresh";
export const STREAM_KEY = "thea_dashboard_stream";
export const REFRESH_OPTIONS = [5, 10, 30, 60];

export function readRefreshSeconds(fallback = 10) {
  const value = Number(localStorage.getItem(REFRESH_KEY));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function readStreamMode(fallback = "live") {
  const value = localStorage.getItem(STREAM_KEY);
  return value === "live" || value === "snapshot" ? value : fallback;
}

export function saveRefreshSeconds(value) {
  localStorage.setItem(REFRESH_KEY, String(value));
}

export function saveStreamMode(value) {
  localStorage.setItem(STREAM_KEY, value);
}
