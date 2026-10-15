import { describe, expect, it } from "vitest"
import type { LiveDuelContestant, LiveDuelView } from "../api/types"
import { assignRank, duelNames, duelPanel, duelShown, feelOrder, finishedText, labelOf, lapsText, statusText, validateFeel } from "./duelLive"

function c(over: Partial<LiveDuelContestant> = {}): LiveDuelContestant {
  return { key: "A", label: "Setup A", name: null, assigned: true, on_car: false, counted: 2, target: 4, raw: 2, skipped: false, status: "driving", last_s: 90, best_s: 89.9, laps: [], ...over }
}
function view(over: Partial<LiveDuelView> = {}): LiveDuelView {
  return {
    phase: "running", track: "Miami", session_type: "FP1", in_garage: false, n: 2, target: 4, min_laps: 3, max_laps: 5,
    compound: 18, compound_label: "C3", contestants: [c(), c({ key: "B", label: "Setup B", assigned: false, counted: 0, status: "waiting" })],
    current: "A", next: "A", instruction: "Setup A: lap 3 of 4", detected: { key: "A", warning: null }, tyre_hint: null,
    question: { pending: false, keys: ["A", "B"] }, feel: null, ranking: null, winner: null, stop_reason: null, feed: [], ...over,
  }
}

describe("duelNames", () => {
  it("trims, pads and cuts to the contestant count", () => {
    expect(duelNames([" Internet A ", ""], 3)).toEqual(["Internet A", "", ""])
    expect(duelNames(["a", "b", "c"], 2)).toEqual(["a", "b"])
    expect(duelNames(["x".repeat(60)], 2)[0]).toHaveLength(40)
  })
})

describe("duelPanel", () => {
  it("picks the panel from the phase and the pending question", () => {
    expect(duelPanel(null)).toBe("start")
    expect(duelPanel(view({ phase: "idle" }))).toBe("start")
    expect(duelPanel(view())).toBe("run")
    expect(duelPanel(view({ question: { pending: true, keys: ["A", "B"] } }))).toBe("feel")
    expect(duelPanel(view({ phase: "review" }))).toBe("review")
    expect(duelPanel(view({ phase: "done" }))).toBe("done")
  })
  it("duelShown is false for null and idle", () => {
    expect(duelShown(undefined)).toBe(false)
    expect(duelShown(view({ phase: "idle" }))).toBe(false)
    expect(duelShown(view())).toBe(true)
  })
})

describe("feel form", () => {
  it("a rank belongs to one contestant at a time", () => {
    let r = assignRank({}, "A", 1)
    r = assignRank(r, "B", 1)
    expect(r).toEqual({ B: 1 })
    r = assignRank(r, "B", 2)
    expect(r).toEqual({ B: 2 })
  })
  it("order needs every key with a distinct rank", () => {
    expect(feelOrder({ A: 1 }, ["A", "B"])).toBeNull()
    expect(feelOrder({ A: 2, B: 1 }, ["A", "B"])).toEqual(["B", "A"])
    expect(feelOrder({ A: 1, B: 1 }, ["A", "B"])).toBeNull()
    expect(feelOrder({ A: 3, B: 1, C: 2 }, ["A", "B", "C"])).toEqual(["B", "C", "A"])
    expect(feelOrder({ A: 1, B: 3 }, ["A", "B"])).toBeNull()
  })
  it("validation text", () => {
    expect(validateFeel({ A: 1 }, ["A", "B"])).toMatch(/own place/)
    expect(validateFeel({ A: 1, B: 2 }, ["A", "B"])).toBeNull()
  })
})

describe("wording", () => {
  it("laps and status", () => {
    expect(lapsText(c({ counted: 6 }))).toBe("4/4")
    const v = view()
    expect(statusText(c({ on_car: true }), v)).toBe("on the car")
    expect(statusText(c(), v)).toBe("drive now")
    expect(statusText(c({ key: "B", assigned: false }), v)).toBe("setup not seen yet")
    expect(statusText(c({ key: "B", status: "done" }), v)).toBe("done")
    expect(statusText(c({ skipped: true }), v)).toBe("skipped")
  })
  it("labels and the finished sentence", () => {
    const v = view({ phase: "done", winner: "B" })
    expect(labelOf(v, "B")).toBe("Setup B")
    expect(labelOf(v, "Z")).toBe("Z")
    expect(finishedText(v)).toMatch(/Setup B is the Miami baseline/)
    expect(finishedText(view({ phase: "done" }))).toMatch(/too little data/)
  })
})
