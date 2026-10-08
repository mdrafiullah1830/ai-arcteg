const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export const API = `${API_BASE}/api/v1`;
export const WS_BASE = API_BASE.replace(/^http/, "ws");

export function getToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("arcteg_token");
}

export function getUser() {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(localStorage.getItem("arcteg_user") || "null");
  } catch {
    return null;
  }
}

export function setSession(token, user) {
  localStorage.setItem("arcteg_token", token);
  localStorage.setItem("arcteg_user", JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem("arcteg_token");
  localStorage.removeItem("arcteg_user");
}

export async function api(path, { method = "GET", body, headers = {} } = {}) {
  const token = getToken();
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export async function login(email, password) {
  const data = await api("/auth/login", { method: "POST", body: { email, password } });
  setSession(data.access_token, {
    name: data.name,
    email: data.email,
    role: data.role,
  });
  return data;
}
