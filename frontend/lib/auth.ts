/** Authentication utilities for admin access. */

const ADMIN_TOKEN_KEY = "agent_admin_token";

export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ADMIN_TOKEN_KEY);
}

export function setAdminToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
}

export function removeAdminToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ADMIN_TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return getAdminToken() !== null;
}

/** Decode JWT payload without verifying signature (safe — only for UI hints). */
export function getTokenPayload(): { sub: string; is_super_admin: boolean } | null {
  const token = getAdminToken();
  if (!token) return null;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    // base64url → base64 → JSON
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

export function getCurrentUserEmail(): string | null {
  return getTokenPayload()?.sub ?? null;
}

export function isSuperAdmin(): boolean {
  return getTokenPayload()?.is_super_admin === true;
}
