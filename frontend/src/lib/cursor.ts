/**
 * One shared cursor per sync group ("lap", "stint", "race"): the map and every trace pane read and write it,
 * so hovering either side moves the other and a click pins the same distance everywhere.
 */
import { create } from "zustand"

export interface CursorGroup {
  hoverX: number | null
  /** Who set hoverX; a component ignores hovers it published itself. */
  hoverSource: string | null
  pinnedX: number | null
}

export const EMPTY_GROUP: CursorGroup = { hoverX: null, hoverSource: null, pinnedX: null }

interface CursorState {
  groups: Record<string, CursorGroup>
  setHover: (group: string, x: number | null, source: string) => void
  setPinned: (group: string, x: number | null) => void
  reset: (group: string) => void
}

export const useCursorStore = create<CursorState>((set) => ({
  groups: {},
  setHover: (group, x, source) =>
    set((s) => {
      const cur = s.groups[group] ?? EMPTY_GROUP
      const src = x == null ? null : source // a cleared hover has no owner
      if (cur.hoverX === x && cur.hoverSource === src) return s
      return { groups: { ...s.groups, [group]: { ...cur, hoverX: x, hoverSource: src } } }
    }),
  setPinned: (group, x) =>
    set((s) => {
      const cur = s.groups[group] ?? EMPTY_GROUP
      if (cur.pinnedX === x) return s
      return { groups: { ...s.groups, [group]: { ...cur, pinnedX: x } } }
    }),
  reset: (group) => set((s) => ({ groups: { ...s.groups, [group]: EMPTY_GROUP } })),
}))

export function selectGroup(group: string) {
  return (s: CursorState): CursorGroup => s.groups[group] ?? EMPTY_GROUP
}

/** Index of the value in an ascending array closest to x. */
export function nearestIndex(sorted: ArrayLike<number | null>, x: number): number {
  let lo = 0
  let hi = sorted.length - 1
  if (hi < 0) return -1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    const v = sorted[mid]
    if ((v ?? -Infinity) < x) lo = mid
    else hi = mid
  }
  const a = sorted[lo]
  const b = sorted[hi]
  if (a == null) return hi
  if (b == null) return lo
  return Math.abs(a - x) <= Math.abs(b - x) ? lo : hi
}
