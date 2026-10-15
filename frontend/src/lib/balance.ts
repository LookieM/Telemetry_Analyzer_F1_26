/** Corners tab balance helpers: relative understeer index, colours, labels and lock-up summaries. Pure, no React. */
import type { BalanceFields, CornerBalance, Lockup, Num, Phase } from "../api/types"
import { scaleColor, type Scale } from "./colors"

export const PHASES: Phase[] = ["entry", "mid", "exit"]
/** Relative index (deg) from which a corner reads as slight / strong understeer or oversteer (same as the server's labels). */
export const SLIGHT_DEG = 0.75
export const STRONG_DEG = 2
/** Relative index at which the heat strip colour is fully saturated. */
export const SCALE_DEG = 3
/** Rear slip ratio on exit at or above which traction is flagged as spinning. */
export const SPIN_RATIO = 0.1

/** Diverging scale: oversteer blue, neutral grey, understeer amber. */
export const BALANCE_SCALE: Scale = [
  [0, "#3E7CC9"],
  [0.5, "#4A4F57"],
  [1, "#E08A1E"],
]

/** Understeer index minus the typical value of its phase (0 = like the library's typical car). */
export function relativeIndex(deg: Num, phase: Phase, baseline: Record<Phase, number>): Num {
  return deg == null ? null : deg - baseline[phase]
}

export function balanceLabel(rel: Num): string {
  if (rel == null) return "no data"
  if (rel >= STRONG_DEG) return "understeer"
  if (rel >= SLIGHT_DEG) return "slight understeer"
  if (rel <= -STRONG_DEG) return "oversteer"
  if (rel <= -SLIGHT_DEG) return "slight oversteer"
  return "neutral"
}

/** Heat strip colour of a relative index; null (no data) gets no colour. */
export function balanceColor(rel: Num): string | null {
  return rel == null ? null : scaleColor(BALANCE_SCALE, (rel + SCALE_DEG) / (2 * SCALE_DEG))
}

export interface BalanceCell {
  value: Num
  rel: Num
  label: string
  color: string | null
}

export interface BalanceColumn {
  id: number
  name: string
  phases: Record<Phase, BalanceCell>
  traction: Num
  lockups: Record<string, number>
}

function cell(deg: Num, phase: Phase, baseline: Record<Phase, number>): BalanceCell {
  const rel = relativeIndex(deg, phase, baseline)
  return { value: deg, rel, label: balanceLabel(rel), color: balanceColor(rel) }
}

/** One column per corner for the phase x corner heat strip. */
export function buildBalanceColumns(corners: { id: number; name: string; balance: CornerBalance | null }[], baseline: Record<Phase, number>): BalanceColumn[] {
  return corners.map((c) => ({
    id: c.id,
    name: c.name,
    phases: {
      entry: cell(c.balance?.entry ?? null, "entry", baseline),
      mid: cell(c.balance?.mid ?? null, "mid", baseline),
      exit: cell(c.balance?.exit ?? null, "exit", baseline),
    },
    traction: c.balance?.traction ?? null,
    lockups: c.balance?.lockups ?? {},
  }))
}

/** Traction is flagged where the rear slip ratio on exit reaches SPIN_RATIO. */
export const isSpinning = (traction: Num): boolean => traction != null && traction >= SPIN_RATIO

/** Lock-up counts per wheel, e.g. { FL: 2, RR: 1 }. */
export function lockupCounts(lockups: Lockup[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const l of lockups) out[l.wheel] = (out[l.wheel] ?? 0) + 1
  return out
}

/** "FL ×2 · RR ×1" or "no lock-ups". */
export function lockupSummary(lockups: Lockup[]): string {
  const counts = lockupCounts(lockups)
  const parts = (["FL", "FR", "RL", "RR"] as const).filter((w) => counts[w]).map((w) => `${w} ×${counts[w]}`)
  return parts.length ? parts.join(" · ") : "no lock-ups"
}

/** One lock-up as a sentence: "FL at 1240 m (T4), 6 m long, lap 7". */
export function lockupText(l: Lockup): string {
  const where = l.corner ? ` (${l.corner.name})` : ""
  const lap = l.lap != null ? `, lap ${l.lap}` : ""
  return `${l.wheel} at ${Math.round(l.distance_m)} m${where}, ${Math.max(1, Math.round(l.length_m))} m long${lap}`
}

/** Why there is no balance to show, or null when there is. */
export function balanceUnavailable(p: Pick<BalanceFields, "balance_available" | "balance_reason"> | undefined): string | null {
  if (!p || p.balance_available) return null
  return p.balance_reason ?? "No balance data"
}
