/** Pure helpers of the track baseline card: garage value text, grouping, copy text, source labels. */
import type { BaselineSource, EngineerBaselineOffer, GarageValue } from "../api/types"

/** "25.5 psi", "65%", "-3.50°", "28": the value as the game's garage shows it. */
export function valueText(v: Pick<GarageValue, "value" | "unit">): string {
  const pct = v.unit.startsWith("%") // "% front" (brake bias) is shown as a plain percentage
  const dec = v.unit === "psi" || v.unit === "°" ? 2 : pct || v.unit === "kg" || Number.isInteger(v.value) ? 0 : 2
  const n = v.value.toFixed(dec).replace("-", "−")
  if (pct) return `${n}%`
  if (v.unit === "°") return `${n}°`
  return v.unit ? `${n} ${v.unit}` : n
}

/** Consecutive values of the same group, in the given order. */
export function groupValues(items: GarageValue[]): { group: string; items: GarageValue[] }[] {
  const out: { group: string; items: GarageValue[] }[] = []
  for (const it of items) {
    const last = out[out.length - 1]
    if (last && last.group === it.group) last.items.push(it)
    else out.push({ group: it.group, items: [it] })
  }
  return out
}

/** Plain text for the clipboard: a title line, then each group heading with its "Label: value" lines. */
export function copyText(title: string, items: GarageValue[]): string {
  const lines = [title]
  for (const g of groupValues(items)) {
    lines.push("", g.group)
    for (const it of g.items) lines.push(`  ${it.label}: ${valueText(it).replace("−", "-")}`)
  }
  return lines.join("\n")
}

const SOURCE_LABELS: Record<BaselineSource, string> = {
  duel: "Setup duel",
  engineer: "Engineer test",
  manual: "Entered by hand",
  library: "Library session",
  generator: "Generated",
}

export function sourceLabel(s: BaselineSource): string {
  return SOURCE_LABELS[s] ?? s
}

/** Name for a baseline made from an engineer program ("Engineer 2026-10-15"). */
export function engineerBaselineName(now: Date = new Date()): string {
  return `Engineer ${now.toISOString().slice(0, 10)}`
}

/** "Front wing 25 → 28, Rear wing 20 → 22" for the engineer's offer. */
export function offerSummary(o: EngineerBaselineOffer): string {
  return o.changed.map((c) => `${c.label} ${c.from} → ${c.to}`).join(", ")
}

/** Write text to the clipboard; false when the browser refuses (never throws). */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
