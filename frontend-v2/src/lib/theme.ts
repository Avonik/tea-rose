import { useCallback, useEffect, useState } from 'react'

export type Theme = 'system' | 'light' | 'dark'
const KEY = 'tearose-theme'

function read(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'light' || v === 'dark') return v
  } catch {
    /* storage unavailable */
  }
  return 'system'
}

function apply(t: Theme) {
  const root = document.documentElement
  if (t === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', t)
}

/** Appearance override. "System" follows the OS; an explicit choice is per browser (Agency). */
export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(read)
  useEffect(() => apply(theme), [theme])
  const set = useCallback((t: Theme) => {
    setTheme(t)
    try {
      if (t === 'system') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, t)
    } catch {
      /* ignore */
    }
  }, [])
  return [theme, set]
}

/** Apply the saved theme before first paint to avoid a flash. Called once from main.tsx. */
export function applySavedTheme() {
  apply(read())
}
