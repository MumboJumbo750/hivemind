import { ref } from 'vue'

type Theme = 'space-neon' | 'industrial-amber' | 'operator-mono'

const STORAGE_KEY = 'hivemind-theme'
const DEFAULT_THEME: Theme = 'space-neon'

const availableThemes: Theme[] = ['space-neon', 'industrial-amber', 'operator-mono']

const stored = localStorage.getItem(STORAGE_KEY) as Theme | null
const currentTheme = ref<Theme>(stored ?? DEFAULT_THEME)

// Initial anwenden
document.documentElement.dataset.theme = currentTheme.value

function setTheme(theme: Theme) {
  currentTheme.value = theme
  document.documentElement.dataset.theme = theme
  localStorage.setItem(STORAGE_KEY, theme)
}

export function useTheme() {
  return { currentTheme, availableThemes, setTheme }
}
