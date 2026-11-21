/** Theme choice: "system" follows the OS; "dark" and "light" pin it via data-theme on <html>. Per browser only. */
export type Theme = "system" | "dark" | "light";
const KEY = "pap.theme";

export const THEME_BOOT = `try{var t=localStorage.getItem("${KEY}");if(t==="dark"||t==="light")document.documentElement.dataset.theme=t}catch(e){}`;

export function getTheme(): Theme {
  try {
    const t = window.localStorage.getItem(KEY);
    return t === "dark" || t === "light" ? t : "system";
  } catch {
    return "system";
  }
}

export function setTheme(t: Theme): void {
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  try {
    if (t === "system") window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, t);
  } catch {
    /* storage unavailable: the choice lasts for this page view only */
  }
}
