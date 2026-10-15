import { describe, expect, it } from "vitest"
import type { DuelContestant, DuelRanking } from "../api/types"
import { balanceCell, balanceDistance, canRank, gapVsLeader, pickHint, setupLabel, togglePick, verdict } from "./duel"

const c = (over: Partial<DuelContestant>): DuelContestant => ({
  key: "a", name: "A", n_laps: 5, rank: 1, race_pace_s: 90, quali_pace_s: 89.5, wear_pct_per_lap: 2, race_cost_s: 0, score_s: 89.85, delta_s: 0, balance: null, ...over,
})
const ranking = (over: Partial<DuelRanking> = {}): DuelRanking => ({
  contestants: [c({}), c({ key: "b", name: "B", rank: 2, score_s: 90.25, delta_s: 0.4 })],
  order: ["a", "b"], winner: "a", tie_break: "stopwatch", decided: true, same_session: true, noise_s: 0.1, pairs: [], weights: { race: 0.7, quali: 0.3 },
  cost_source: "model", cost_note: "", callouts: [], ...over,
})

describe("setupLabel", () => {
  it("uses the name or the short fingerprint", () => {
    expect(setupLabel({ fingerprint: "abcdef123456", name: " Internet A " })).toBe("Internet A")
    expect(setupLabel({ fingerprint: "abcdef123456", name: null })).toBe("Setup abcdef")
    expect(setupLabel({ fingerprint: "abcdef123456", name: "  " })).toBe("Setup abcdef")
  })
})

describe("togglePick", () => {
  it("adds, removes and keeps at most three", () => {
    expect(togglePick([], "a")).toEqual(["a"])
    expect(togglePick(["a", "b"], "a")).toEqual(["b"])
    expect(togglePick(["a", "b", "c"], "d")).toEqual(["b", "c", "d"])
  })
  it("allows ranking with two or three picks only", () => {
    expect([[], ["a"], ["a", "b"], ["a", "b", "c"]].map(canRank)).toEqual([false, false, true, true])
    expect(pickHint(0)).toMatch(/Pick 2 more setups/)
    expect(pickHint(1)).toMatch(/Pick 1 more setup to/)
    expect(pickHint(2)).toBe("2 picked")
  })
})

describe("verdict", () => {
  it("names the winner, gap and the deciding rule", () => {
    expect(verdict(ranking())).toBe("A wins by 0.400 s per lap: decided by the stopwatch")
    expect(verdict(ranking({ tie_break: "balance" }))).toBe("A wins: inside the noise, decided by balance")
  })
  it("says so when nothing is measurable", () => {
    expect(verdict(ranking({ tie_break: "none", decided: false }))).toBe("No measurable difference between A and B")
  })
})

describe("gapVsLeader", () => {
  it("flags gaps against the noise band", () => {
    expect(gapVsLeader(c({}), 0.1).text).toBe("leader")
    expect(gapVsLeader(c({ rank: 2, delta_s: 0.4 }), 0.1)).toEqual({ text: "+0.400 s · measurable", measurable: true })
    expect(gapVsLeader(c({ rank: 2, delta_s: 0.05 }), 0.1)).toEqual({ text: "+0.050 s · within noise", measurable: false })
  })
})

describe("balance cells", () => {
  const bal = { entry: { deg: 2, relative: 0, label: "neutral" }, mid: { deg: 5, relative: 2, label: "understeer" }, exit: { deg: null, relative: null, label: null }, distance: 2.04 }
  it("shows labels and the distance from neutral", () => {
    expect(balanceCell(bal, "mid")).toBe("understeer")
    expect(balanceCell(bal, "exit")).toBe("—")
    expect(balanceCell(null, "entry")).toBe("—")
    expect(balanceDistance(bal)).toBe("2.04°")
    expect(balanceDistance(null)).toBe("—")
  })
})
