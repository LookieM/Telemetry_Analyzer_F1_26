import type { LapSummary, SessionMeta } from "../api/types"

export interface SessionFilter {
  track: string
  type: string
  query: string
}

/** Library filters: exact track, session type ("(untagged)" = none), free-text over file / car / notes. */
export function filterSessions(all: SessionMeta[], f: SessionFilter): SessionMeta[] {
  const q = f.query.trim().toLowerCase()
  return all.filter((s) => {
    if (f.track && s.track !== f.track) return false
    if (f.type === "(untagged)" && (s.session_type ?? "").trim() !== "") return false
    if (f.type && f.type !== "(untagged)" && s.session_type !== f.type) return false
    if (q) {
      const hay = [s.source_name, s.car, s.track, s.notes, s.conditions, s.session_type].join(" ").toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
}

/** Personal-best session among `candidates` (lowest best lap time), or null. */
export function pbSession(candidates: SessionMeta[]): SessionMeta | null {
  let best: SessionMeta | null = null
  for (const s of candidates) {
    if (s.best_lap_time == null) continue
    if (!best || s.best_lap_time < (best.best_lap_time ?? Infinity)) best = s
  }
  return best
}

/** Lap number of the fastest lap in a lap summary (falls back to the first lap). */
export function bestLapNumber(laps: LapSummary[]): number | null {
  const best = laps.find((l) => l.is_best)
  return best ? best.lap : (laps[0]?.lap ?? null)
}

/** Dropdown label for a lap: "Lap 33 — 1:06.154 ★". */
export function lapLabel(lap: LapSummary, fmtTime: (s: number) => string): string {
  return `Lap ${lap.lap} — ${fmtTime(lap.lap_time)}${lap.is_best ? " ★" : ""}${lap.lap_class && lap.lap_class !== "push" ? ` (${lap.lap_class})` : ""}`
}

/** Fastest lap other than `exclude`, preferring clean ("push") laps; null when there is none. */
export function fastestOtherLap(laps: LapSummary[], exclude: number | null): number | null {
  const others = laps.filter((l) => l.lap !== exclude && Number.isFinite(l.lap_time) && l.lap_time > 0)
  const pool = others.some((l) => l.lap_class === "push") ? others.filter((l) => l.lap_class === "push") : others
  return pool.reduce<LapSummary | null>((b, l) => (b == null || l.lap_time < b.lap_time ? l : b), null)?.lap ?? null
}
