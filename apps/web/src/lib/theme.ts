/**
 * Theme choice: "system" follows the OS; "dark" and "light" pin it via data-theme on <html>.
 *
 * Kept in a cookie, not browser storage: browser storage is reserved by policy (Semgrep rule
 * pap-token-in-browser-storage), and the cookie lets the server render the right theme on the first byte, with no
 * inline script. It is a display preference, not a credential: readable by the page, SameSite=Lax, one year.
 */
export type Theme = "system" | "dark" | "light";
export const THEME_COOKIE = "pap_theme";

export function parseTheme(v: string | undefined | null): Theme {
  return v === "dark" || v === "light" ? v : "system";
}

export function getTheme(): Theme {
  const m = typeof document === "undefined" ? null : document.cookie.match(/(?:^|;\s*)pap_theme=(dark|light)/);
  return parseTheme(m?.[1]);
}

export function setTheme(t: Theme): void {
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  const age = t === "system" ? 0 : 365 * 24 * 3600;
  document.cookie = `${THEME_COOKIE}=${t === "system" ? "" : t}; Path=/; Max-Age=${age}; SameSite=Lax`;
}
