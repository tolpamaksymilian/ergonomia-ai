export const THEME_STORAGE_KEY = "ergonomia-ai-theme";
export type AppTheme = "light" | "dark";
type ThemeStorage = Pick<Storage, "getItem" | "setItem">;

export function normalizeTheme(value: unknown): AppTheme { return value === "dark" ? "dark" : "light"; }
export function oppositeTheme(theme: AppTheme): AppTheme { return theme === "light" ? "dark" : "light"; }
export function readStoredTheme(storage: Pick<ThemeStorage, "getItem">): AppTheme { return normalizeTheme(storage.getItem(THEME_STORAGE_KEY)); }
export function persistTheme(storage: Pick<ThemeStorage, "setItem">, theme: AppTheme) { storage.setItem(THEME_STORAGE_KEY, theme); }
export function themeBootstrapScript() {
  return `(function(){try{var key=${JSON.stringify(THEME_STORAGE_KEY)};var value=localStorage.getItem(key);var theme=value==='dark'?'dark':'light';var root=document.documentElement;root.classList.toggle('dark',theme==='dark');root.dataset.theme=theme;root.style.colorScheme=theme;}catch(_){document.documentElement.dataset.theme='light';document.documentElement.style.colorScheme='light';}})();`;
}
