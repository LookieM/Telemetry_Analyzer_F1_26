/** Which optional lap-trace panes are switched on: pure helpers plus a per-browser memory of the choice. */
import type { LapExtra } from "../api/types"

const KEY = "telemetria.lapExtras"

export function loadExtras(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]")
    return Array.isArray(raw) ? raw.filter((k): k is string => typeof k === "string") : []
  } catch {
    return []
  }
}

export function saveExtras(keys: string[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(keys))
  } catch {
    /* storage unavailable: the choice just is not remembered */
  }
}

/** The picked extras this session can actually show (nothing until availability is known). */
export function usableExtras(picked: string[], info: LapExtra[] | undefined): string[] {
  if (!info) return []
  const ok = new Set(info.filter((e) => e.available).map((e) => e.key))
  return info.map((e) => e.key).filter((k) => ok.has(k) && picked.includes(k))
}
