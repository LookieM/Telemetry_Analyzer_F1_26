/** Coach feed helpers. Pure, no React. */
import type { CoachItem } from "../api/types"

export const ACTION_LABEL: Record<CoachItem["action_kind"], string> = {
  drive: "Drive",
  setup: "Setup",
  manage: "Manage",
  observe: "Observe",
}

/** The remaining callouts grouped by domain (alphabetical), each group in score order. */
export function groupByDomain(items: CoachItem[]): { domain: string; items: CoachItem[] }[] {
  const by = new Map<string, CoachItem[]>()
  for (const it of items) {
    const list = by.get(it.domain) ?? []
    list.push(it)
    by.set(it.domain, list)
  }
  return [...by.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([domain, list]) => ({ domain, items: [...list].sort((x, y) => y.score - x.score) }))
}

export function titleCase(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s
}
