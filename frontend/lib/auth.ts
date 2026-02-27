/** Authentication utilities for admin access. */

const ADMIN_TOKEN_KEY = "agent_admin_token";

/**
 * Get admin token from localStorage.
 */
export function getAdminToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(ADMIN_TOKEN_KEY);
}

/**
 * Set admin token in localStorage.
 */
export function setAdminToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
}

/**
 * Remove admin token from localStorage.
 */
export function removeAdminToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.removeItem(ADMIN_TOKEN_KEY);
}

/**
 * Check if admin is authenticated.
 */
export function isAuthenticated(): boolean {
  return getAdminToken() !== null;
}






