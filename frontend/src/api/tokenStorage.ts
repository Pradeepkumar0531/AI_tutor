/**
 * Centralized token storage. This is the ONLY module that touches the raw
 * credential: the Axios client reads it for the Authorization header and the
 * auth store writes/clears it on login/logout. No React component imports this.
 *
 * Strategy: short-lived Bearer access token in localStorage (no refresh
 * tokens in this phase). Tradeoff is documented in docs/SECURITY.md.
 */

const TOKEN_KEY = "alc.access_token";

export { TOKEN_KEY };

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage unavailable (private mode): session simply won't persist.
  }
}

export function clearStoredToken(): void {
  setStoredToken(null);
}
