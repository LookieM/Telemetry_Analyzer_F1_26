/** Fit the racing line (and the circuit outline) into a canvas; nearest-point lookup for hover. */
import type { Num } from "../api/types"

export interface Projection {
  px: number[]
  py: number[]
  ox: number[]
  oy: number[]
}

export const MAP_PAD = 22
export const HOVER_RADIUS_PX = 36

export function projectTrack(
  x: Num[],
  y: Num[],
  outline: { x: number[]; y: number[] } | null,
  w: number,
  h: number,
  pad = MAP_PAD,
): Projection {
  const ox0 = outline?.x ?? []
  const oy0 = outline?.y ?? []
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  const take = (xs: ArrayLike<Num>, ys: ArrayLike<Num>) => {
    for (let i = 0; i < xs.length; i++) {
      const a = xs[i]
      const b = ys[i]
      if (a == null || b == null) continue
      if (a < minX) minX = a
      if (a > maxX) maxX = a
      if (b < minY) minY = b
      if (b > maxY) maxY = b
    }
  }
  take(x, y)
  take(ox0, oy0)
  if (!Number.isFinite(minX)) return { px: [], py: [], ox: [], oy: [] }
  const k = Math.min((w - 2 * pad) / Math.max(1e-6, maxX - minX), (h - 2 * pad) / Math.max(1e-6, maxY - minY))
  const offX = (w - k * (maxX - minX)) / 2
  const offY = (h - k * (maxY - minY)) / 2
  const sx = (v: number) => offX + (v - minX) * k
  const sy = (v: number) => offY + (maxY - v) * k // world Y up, canvas Y down
  return {
    px: x.map((v) => (v == null ? NaN : sx(v))),
    py: y.map((v) => (v == null ? NaN : sy(v))),
    ox: ox0.map(sx),
    oy: oy0.map(sy),
  }
}

/** Index of the projected point nearest to (mx, my) within `radius` pixels, else null. */
export function nearestOnScreen(px: number[], py: number[], mx: number, my: number, radius = HOVER_RADIUS_PX): number | null {
  let best = -1
  let bestD = Infinity
  for (let i = 0; i < px.length; i++) {
    const dx = px[i] - mx
    const dy = py[i] - my
    const dd = dx * dx + dy * dy
    if (dd < bestD) {
      bestD = dd
      best = i
    }
  }
  return best >= 0 && bestD <= radius * radius ? best : null
}
