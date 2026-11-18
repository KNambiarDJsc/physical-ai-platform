/**
 * Development identity only (the API's PAP_AUTH_MODE=dev). Browser OIDC login is a separate feature (AUTH-002);
 * until it exists the web app says so instead of pretending to authenticate.
 */
const KEY = "pap.dev-identity";

export function getIdentity(): string | null {
  try {
    const v = typeof window === "undefined" ? null : window.sessionStorage.getItem(KEY);
    return v ? `dev:${v}` : null;
  } catch {
    return null;
  }
}

export function setIdentity(subject: string | null): void {
  try {
    if (subject) window.sessionStorage.setItem(KEY, subject);
    else window.sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the user stays signed out */
  }
}
