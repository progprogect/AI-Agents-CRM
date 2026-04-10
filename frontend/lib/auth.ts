/** Authentication utilities for admin access — multitenancy-aware. */

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

export type UserRole = "owner" | "admin" | "member";

export interface TokenPayload {
  sub: string;
  /** Backward compat */
  is_super_admin: boolean;
  /** Multitenancy */
  org_id: string | null;
  role: UserRole | null;
  is_platform_admin: boolean;
  iat: number;
  exp: number;
}

/** Decode JWT payload without verifying signature (safe — only for UI hints). */
export function getTokenPayload(): TokenPayload | null {
  const token = getAdminToken();
  if (!token) return null;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64)) as TokenPayload;
  } catch {
    return null;
  }
}

export function getCurrentUserEmail(): string | null {
  return getTokenPayload()?.sub ?? null;
}

export function isSuperAdmin(): boolean {
  const p = getTokenPayload();
  return p?.is_platform_admin === true || p?.is_super_admin === true;
}

export function isPlatformAdmin(): boolean {
  return getTokenPayload()?.is_platform_admin === true;
}

export function getOrgId(): string | null {
  return getTokenPayload()?.org_id ?? null;
}

export function getUserRole(): UserRole | null {
  return getTokenPayload()?.role ?? null;
}

/** Can create / edit / delete agents and channels. */
export function canManageAgents(): boolean {
  if (isPlatformAdmin()) return true;
  const role = getUserRole();
  return role === "owner" || role === "admin";
}

/** Can manage LLM API keys (openai, google). Only owners. */
export function canManageKeys(): boolean {
  if (isPlatformAdmin()) return true;
  return getUserRole() === "owner";
}

/** Can invite / remove team members. */
export function canManageTeam(): boolean {
  if (isPlatformAdmin()) return true;
  const role = getUserRole();
  return role === "owner" || role === "admin";
}

/** Can view conversations and chat (any authenticated member). */
export function canViewConversations(): boolean {
  return isAuthenticated();
}
