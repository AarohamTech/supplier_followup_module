// Tiny token store shared by the API client and the auth context.
// Kept dependency-free to avoid import cycles (api.ts ↔ auth.tsx).
const TOKEN_KEY = "sfa_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export const LOGIN_PATH = "/login";
