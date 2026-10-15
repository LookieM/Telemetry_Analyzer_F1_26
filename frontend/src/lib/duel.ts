/** Setups page helpers: picking contestants, labels and wording of the duel result. */
import type { DuelBalance, DuelContestant, DuelRanking, DuelTieBreak, SetupCandidate } from "../api/types"
import { fmt, fmtSigned, isNum } from "./format"

export const MIN_PICK = 2
export const MAX_PICK = 3

/** The name the user gave, else "Setup <first 6 of the fingerprint>" (same as the server). */
export function setupLabel(s: Pick<SetupCandidate, "fingerprint" | "name">): string {
  return s.name?.trim() || `Setup ${s.fingerprint.slice(0, 6)}`
}

/** Tick / untick a setup; at most MAX_PICK stay picked (the oldest pick drops out). */
export function togglePick(picked: string[], fingerprint: string): string[] {
  if (picked.includes(fingerprint)) return picked.filter((f) => f !== fingerprint)
  return [...picked, fingerprint].slice(-MAX_PICK)
}

export function pickHint(n: number): string {
  if (n < MIN_PICK) return `Pick ${MIN_PICK - n} more setup${MIN_PICK - n === 1 ? "" : "s"} to compare (2–${MAX_PICK})`
  return `${n} picked`
}

export const canRank = (picked: string[]) => picked.length >= MIN_PICK && picked.length <= MAX_PICK

export const TIE_BREAK_TEXT: Record<DuelTieBreak, string> = {
  stopwatch: "decided by the stopwatch",
  balance: "inside the noise, decided by balance",
  feel: "inside the noise, decided by your feel",
  none: "no measurable difference",
}

/** One headline for the result, e.g. "Monza A wins by 0.412 s per lap: decided by the stopwatch". */
export function verdict(r: DuelRanking): string {
  const [first, second] = r.contestants
  if (!r.decided) return `No measurable difference between ${r.contestants.map((c) => c.name).join(" and ")}`
  const gap = second ? second.score_s - first.score_s : 0
  const by = r.tie_break === "stopwatch" ? ` by ${gap.toFixed(3)} s per lap` : ""
  return `${first.name} wins${by}: ${TIE_BREAK_TEXT[r.tie_break]}`
}

/** Gap to the leader in score and whether it is outside the noise band. */
export function gapVsLeader(c: DuelContestant, noise: number): { text: string; measurable: boolean | null } {
  if (c.rank === 1 || c.delta_s === 0) return { text: "leader", measurable: null }
  const measurable = c.delta_s > noise
  return { text: `${fmtSigned(c.delta_s, 3)} s · ${measurable ? "measurable" : "within noise"}`, measurable }
}

export function balanceCell(b: DuelBalance | null, phase: "entry" | "mid" | "exit"): string {
  return b?.[phase]?.label ?? "—"
}

export function balanceDistance(b: DuelBalance | null): string {
  return b && isNum(b.distance) ? `${fmt(b.distance, 2)}°` : "—"
}

export function wearText(v: number | null): string {
  return isNum(v) ? `${fmt(v, 2)} %/lap` : "—"
}
