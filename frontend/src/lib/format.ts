/** Number / time formatting shared by every view. */

export const DASH = "—"

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v)
}

/** Fixed decimals, "—" for null / NaN. */
export function fmt(v: number | null | undefined, decimals = 1): string {
  return isNum(v) ? v.toFixed(decimals) : DASH
}

/** Always-signed fixed decimals ("+0.123", "-1.5"); zero stays unsigned-plus. */
export function fmtSigned(v: number | null | undefined, decimals = 3): string {
  if (!isNum(v)) return DASH
  const s = v.toFixed(decimals)
  return v > 0 && Number(s) !== 0 ? `+${s}` : s
}

/** Lap time: 1:06.154 or 59.842s (same as the Streamlit `format_lap_time`). */
export function formatLapTime(seconds: number | null | undefined): string {
  if (!isNum(seconds)) return DASH
  const m = Math.floor(seconds / 60)
  const s = seconds - m * 60
  return m ? `${m}:${s.toFixed(3).padStart(6, "0")}` : `${s.toFixed(3)}s`
}

/** Race time: 42:18.563 or 1:02:03.250. */
export function formatRaceTime(seconds: number | null | undefined): string {
  if (!isNum(seconds)) return DASH
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds - h * 3600) / 60)
  const s = seconds - h * 3600 - m * 60
  const sec = s.toFixed(3).padStart(6, "0")
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`
}

export function formatBytes(n: number | null | undefined): string {
  if (!isNum(n)) return DASH
  const units = ["B", "KB", "MB", "GB"]
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

/** "2026-10-09T13:24:20+00:00" -> "2026-10-09". */
export function formatDate(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10) : DASH
}

/** Box windows: "L8 (7–9), L22". */
export function windowsText(stopLaps: number[], windows: number[][]): string {
  const parts = stopLaps.map((lap, i) => {
    const w = windows[i]
    return `L${lap}` + (w && (w[0] !== lap || w[1] !== lap) ? ` (${w[0]}–${w[1]})` : "")
  })
  return parts.join(", ") || "no stop"
}
