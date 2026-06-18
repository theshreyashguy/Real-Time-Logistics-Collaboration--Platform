// Token storage + refresh. Tokens live in localStorage for the demo; in
// production prefer httpOnly cookies (see DEPLOYMENT.md security notes).
import { xhrRequest } from "./xhr";

const ACCESS = "hemut_access";
const REFRESH = "hemut_refresh";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS, access);
  localStorage.setItem(REFRESH, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS);
  localStorage.removeItem(REFRESH);
}

export async function tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const res = await xhrRequest<{ access_token: string; refresh_token: string }>(
      "/auth/refresh",
      { method: "POST", body: { refresh_token: refresh } }
    );
    setTokens(res.access_token, res.refresh_token);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}
