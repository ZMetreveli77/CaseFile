// Light or dark. With no saved choice the page follows the system setting (CSS prefers-color-scheme);
// a choice made with the toggle is saved and set as <html data-theme="...">, which the CSS checks first.
export type Theme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'casefile-theme'

export function readSavedTheme(): Theme | null {
  try {
    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY)
    return savedTheme === 'light' || savedTheme === 'dark' ? savedTheme : null
  } catch {
    return null // storage can be blocked (private mode); then we just follow the system
  }
}

export function readSystemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // not saved; the choice still applies for this visit
  }
}
