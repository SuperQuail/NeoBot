export type ThemePreference = 'light' | 'dark' | 'auto';
const THEME_KEY = 'neobot-dashboard-theme';
export function getThemePreference(): ThemePreference {
  const saved = localStorage.getItem(THEME_KEY);
  return saved === 'light' || saved === 'dark' ? saved : 'auto';
}
export function applyTheme(preference: ThemePreference): void {
  const systemDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
  document.documentElement.dataset.theme =
    preference === 'auto' ? (systemDark ? 'dark' : 'light') : preference;
  document.documentElement.dataset.themePreference = preference;
}
export function setThemePreference(preference: ThemePreference): void {
  localStorage.setItem(THEME_KEY, preference);
  applyTheme(preference);
  window.dispatchEvent(new Event('dashboard-theme-change'));
}
export function initializeTheme(): () => void {
  applyTheme(getThemePreference());
  const media = window.matchMedia?.('(prefers-color-scheme: dark)');
  const sync = () => applyTheme(getThemePreference());
  media?.addEventListener?.('change', sync);
  window.addEventListener('storage', sync);
  return () => {
    media?.removeEventListener?.('change', sync);
    window.removeEventListener('storage', sync);
  };
}
