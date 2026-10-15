/** Corners tab helpers: table rows, sorting, zoom window, loss colouring and trace markers. Pure, no React. */
import type { CornersPayload, Num, SpeedClass } from "../api/types"
import { BRAKE, NEUTRAL, THROTTLE } from "./colors"
import type { Marker } from "./traces"

/** A corner time difference below this (s) is noise: neither a loss nor a gain. */
export const NOISE_S = 0.03
/** Metres of track kept around a corner when the map and traces zoom to it. */
export const ZOOM_MARGIN_M = 60

export interface CornerRow {
  id: number
  order: number
  name: string
  speedClass: SpeedClass
  startM: number
  endM: number
  apexM: number
  complex: boolean
  time: Num
  timeDelta: Num
  entry: Num
  entryDelta: Num
  vmin: Num
  vminDelta: Num
  exit: Num
  exitDelta: Num
  brake: Num
  brakeDelta: Num
  trail: Num
  trailDelta: Num
  throttle: Num
  throttleDelta: Num
  callouts: string[]
  /** Focus-lap and reference-lap brake / full-throttle points (m), for the trace markers. */
  points: { brake: Num; throttle: Num; refBrake: Num; refThrottle: Num }
}

export type SortKey = "order" | "timeDelta" | "time" | "entry" | "vmin" | "exit" | "brake" | "trail" | "throttle"
export type SortDir = "asc" | "desc"

export function buildCornerRows(p: CornersPayload): CornerRow[] {
  return p.corners.map((c, i) => ({
    id: c.id,
    order: i + 1,
    name: c.name,
    speedClass: c.speed_class,
    startM: c.start_m,
    endM: c.end_m,
    apexM: c.apex_m,
    complex: c.merged_from.length > 1,
    time: c.focus.time_s,
    timeDelta: c.delta.time_s,
    entry: c.focus.entry_kmh,
    entryDelta: c.delta.entry_kmh,
    vmin: c.focus.vmin_kmh,
    vminDelta: c.delta.vmin_kmh,
    exit: c.focus.exit_kmh,
    exitDelta: c.delta.exit_kmh,
    brake: c.focus.brake_m,
    brakeDelta: c.delta.brake_m,
    trail: c.focus.trail_m,
    trailDelta: c.delta.trail_m,
    throttle: c.focus.throttle_m,
    throttleDelta: c.delta.throttle_m,
    callouts: c.callouts,
    points: { brake: c.focus.brake_m, throttle: c.focus.throttle_m, refBrake: c.ref.brake_m, refThrottle: c.ref.throttle_m },
  }))
}

/** Sorted copy; corners without a value for the key go last in either direction. */
export function sortRows(rows: CornerRow[], key: SortKey, dir: SortDir): CornerRow[] {
  const sign = dir === "asc" ? 1 : -1
  return [...rows].sort((a, b) => {
    const x = a[key]
    const y = b[key]
    if (x == null && y == null) return a.order - b.order
    if (x == null) return 1
    if (y == null) return -1
    return x === y ? a.order - b.order : sign * (x - y)
  })
}

/** Distance window to zoom to: the corner plus a margin on both sides, kept inside [0, trackLength]. */
export function zoomRange(c: { startM: number; endM: number }, trackLength: number | null, margin = ZOOM_MARGIN_M): [number, number] {
  const from = Math.max(0, c.startM - margin)
  const to = c.endM + margin
  return [from, trackLength != null ? Math.min(trackLength, to) : to]
}

export type LossKind = "loss" | "gain" | "flat"

/** Colour class of a corner time difference (positive = slower than the reference). */
export function lossKind(delta: Num, threshold = NOISE_S): LossKind {
  if (delta == null || Math.abs(delta) < threshold) return "flat"
  return delta > 0 ? "loss" : "gain"
}

/** Brake-point and full-throttle markers of a corner: focus lap in colour, reference lap grey. */
export function cornerMarkers(row: CornerRow): Marker[] {
  const out: Marker[] = []
  const add = (x: Num, label: string, color: string) => {
    if (x != null) out.push({ x, label, color })
  }
  add(row.points.brake, "Brake", BRAKE)
  add(row.points.throttle, "Full throttle", THROTTLE)
  add(row.points.refBrake, "Brake (ref)", NEUTRAL)
  add(row.points.refThrottle, "Full thr (ref)", NEUTRAL)
  return out
}

/** The corner with the biggest time loss above the noise, or null. */
export function biggestLoss(rows: CornerRow[]): CornerRow | null {
  let best: CornerRow | null = null
  for (const r of rows) if (r.timeDelta != null && r.timeDelta >= NOISE_S && (!best || r.timeDelta > (best.timeDelta ?? 0))) best = r
  return best
}

/** Name of the corner a distance falls in, or null on a straight. */
export function cornerAt(rows: Pick<CornerRow, "startM" | "endM" | "name">[], x: number | null): string | null {
  if (x == null) return null
  return rows.find((r) => x >= r.startM && x <= r.endM)?.name ?? null
}
