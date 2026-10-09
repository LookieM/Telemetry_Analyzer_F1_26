import { useSyncExternalStore } from "react"

export type Theme = "dark" | "light"
const KEY = "telemetria-theme"

function read(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark"
}

export function initTheme(): void {
  let saved: string | null = null
  try {
    saved = localStorage.getItem(KEY)
  } catch {
    /* storage blocked */
  }
  document.documentElement.dataset.theme = saved === "light" ? "light" : "dark"
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* storage blocked */
  }
}

function subscribe(cb: () => void): () => void {
  const obs = new MutationObserver(cb)
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] })
  return () => obs.disconnect()
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, read, () => "dark")
}
