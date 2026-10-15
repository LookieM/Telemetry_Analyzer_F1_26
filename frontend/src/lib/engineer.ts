/** Pure helpers of the Live page's Engineer card: labels, number formatting, answer validation, panel choice. */
import type { EngineerAnswer, EngineerResult, EngineerVariant, EngineerView } from "../api/types"

export const MAX_TAGS = 3

const TAG_LABELS: Record<string, string> = {
  entry_slow: "Entry · slow corners",
  entry_fast: "Entry · fast corners",
  mid_slow: "Mid · slow corners",
  mid_fast: "Mid · fast corners",
  exit_slow: "Exit · slow corners",
  exit_fast: "Exit · fast corners",
  braking_stability: "Braking stability",
  braking_lockups: "Brake lock-ups",
  traction: "Traction",
  kerbs: "Kerbs",
  confidence: "Confidence",
}

export function tagLabel(id: string): string {
  return TAG_LABELS[id] ?? id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())
}

/** "m:ss" for a time budget; "—" when unknown. */
export function fmtBudget(s: number | null | undefined): string {
  if (s == null || !Number.isFinite(s)) return "—"
  const t = Math.max(0, Math.round(s))
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`
}

/** Signed seconds with a real minus sign, e.g. "+0.123" / "−0.050". */
export function fmtDelta(s: number | null | undefined, digits = 3): string {
  if (s == null || !Number.isFinite(s)) return "—"
  const r = Math.abs(s).toFixed(digits)
  if (Number(r) === 0) return (0).toFixed(digits)
  return `${s > 0 ? "+" : "−"}${r}`
}

/** Plain-English stopwatch line for a result (variant 2 minus variant 1; negative = 2 faster). */
export function stopwatchLine(r: Pick<EngineerResult, "delta_s" | "noise_s" | "measurable" | "stopwatch_winner">): string {
  if (r.delta_s == null) return "No stopwatch comparison yet"
  const noise = r.noise_s != null ? ` (noise ±${r.noise_s.toFixed(2)} s)` : ""
  if (!r.measurable || !r.stopwatch_winner) return `No measurable difference: ${fmtDelta(r.delta_s, 2)} s/lap${noise}`
  return `Variant ${r.stopwatch_winner} faster by ${Math.abs(r.delta_s).toFixed(3)} s/lap${noise}`
}

export function confidenceLabel(c: string | null | undefined): string {
  return c === "high" ? "high confidence" : c === "medium" ? "medium confidence" : "low confidence"
}

export function toggleTag(tags: string[], tag: string, max = MAX_TAGS): string[] {
  if (tags.includes(tag)) return tags.filter((t) => t !== tag)
  return tags.length >= max ? tags : [...tags, tag]
}

/** null when the answer can be sent, else the reason it cannot. */
export function validateAnswer(a: { verdict: string | null; strength: string | null; tags: string[] }, allowedTags: string[]): string | null {
  if (a.verdict !== "1" && a.verdict !== "2" && a.verdict !== "same") return "Pick 1, 2 or Same first"
  if (a.strength !== "slight" && a.strength !== "clear") return "Pick how strong the difference was"
  if (a.tags.length > MAX_TAGS) return `At most ${MAX_TAGS} tags`
  if (new Set(a.tags).size !== a.tags.length) return "Duplicate tags"
  const bad = a.tags.find((t) => !allowedTags.includes(t))
  if (bad) return `Unknown tag: ${bad}`
  return null
}

export function buildAnswer(a: { verdict: "1" | "2" | "same"; strength: "slight" | "clear"; tags: string[]; note: string }): EngineerAnswer {
  const note = a.note.trim()
  return { verdict: a.verdict, strength: a.strength, tags: a.tags, ...(note ? { note } : {}) }
}

export type EngineerPanel = "start" | "revert" | "confirm" | "question" | "run" | "quali" | "long_run" | "done"

/** Which main panel the card shows for a view (null view or idle = start). */
export function engineerPanel(v: EngineerView | null | undefined): EngineerPanel {
  if (!v || v.phase === "idle") return "start"
  if (v.revert_proposal) return "revert"
  if (v.question.awaiting_confirm) return "confirm"
  if (v.question.pending) return "question"
  if (v.phase === "done") return "done"
  if (v.phase === "long_run") return "long_run"
  if (v.phase === "quali") return "quali"
  return "run"
}

export const PHASE_LABEL: Record<string, string> = { balance: "Balance", quali: "Quali check", long_run: "Long run", done: "Finished", idle: "Idle" }

/** Value shown for a variant: its text, else its display number, else "reference". */
export function variantValue(v: Pick<EngineerView, "variant_text" | "variants">, which: EngineerVariant): string {
  const t = v.variant_text?.[which]
  if (t) return t
  const x = v.variants?.[which]
  return x == null ? "reference" : String(x)
}

/** Error text for a failed command (409 carries the engineer's reason). */
export function commandError(status: number | null, message: string): string {
  if (status === 503) return "Live telemetry is disabled on the server"
  if (status === 401) return "Access token needed - open the page with ?token=..."
  return message || "Command failed"
}
