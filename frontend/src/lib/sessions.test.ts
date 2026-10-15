import { describe, expect, it } from "vitest"
import type { LapSummary, SessionMeta } from "../api/types"
import { bestLapNumber, fastestOtherLap, filterSessions, lapLabel, pbSession } from "./sessions"

const base = { sample_count: 1, car: "Mercedes", notes: "", conditions: "", lap_count: 10, best_lap: 1, original_size_bytes: 1, stored_size_bytes: 1, created_at: "", track_length: 1000 }
const sessions: SessionMeta[] = [
  { ...base, id: 1, source_name: "Austria_race.csv", track: "Austria", session_type: "Race", best_lap_time: 66.2 },
  { ...base, id: 2, source_name: "Austria_practice.csv", track: "Austria", session_type: "", best_lap_time: 65.9 },
  { ...base, id: 3, source_name: "Monza_Q3.csv", track: "Monza", session_type: "Quali", best_lap_time: null, notes: "wet start" },
]

describe("filterSessions", () => {
  it("filters by track and type", () => {
    expect(filterSessions(sessions, { track: "Austria", type: "", query: "" }).map((s) => s.id)).toEqual([1, 2])
    expect(filterSessions(sessions, { track: "", type: "Quali", query: "" }).map((s) => s.id)).toEqual([3])
    expect(filterSessions(sessions, { track: "", type: "(untagged)", query: "" }).map((s) => s.id)).toEqual([2])
  })
  it("searches file names, notes and car case-insensitively", () => {
    expect(filterSessions(sessions, { track: "", type: "", query: "PRACTICE" }).map((s) => s.id)).toEqual([2])
    expect(filterSessions(sessions, { track: "", type: "", query: "wet" }).map((s) => s.id)).toEqual([3])
    expect(filterSessions(sessions, { track: "", type: "", query: "nothing" })).toEqual([])
  })
})

describe("pbSession", () => {
  it("picks the lowest best lap and ignores sessions without one", () => {
    expect(pbSession(sessions)?.id).toBe(2)
    expect(pbSession([sessions[2]])).toBeNull()
  })
})

describe("laps", () => {
  const laps = [
    { lap: 0, lap_time: 70, lap_class: "start", pit_stop: false, delta_best: 4, is_best: false },
    { lap: 5, lap_time: 66.154, lap_class: "push", pit_stop: false, delta_best: 0, is_best: true },
  ] as LapSummary[]
  it("finds the best lap", () => {
    expect(bestLapNumber(laps)).toBe(5)
    expect(bestLapNumber([])).toBeNull()
  })
  it("labels laps with their class unless push", () => {
    expect(lapLabel(laps[1], (s) => `${s}s`)).toBe("Lap 5 — 66.154s ★")
    expect(lapLabel(laps[0], (s) => `${s}s`)).toBe("Lap 0 — 70s (start)")
  })
})

describe("fastestOtherLap", () => {
  const laps = [
    { lap: 1, lap_time: 65.0, lap_class: "out", pit_stop: false, delta_best: 0, is_best: false },
    { lap: 2, lap_time: 66.1, lap_class: "push", pit_stop: false, delta_best: 0, is_best: true },
    { lap: 3, lap_time: 66.4, lap_class: "push", pit_stop: false, delta_best: 0.3, is_best: false },
  ] as LapSummary[]
  it("picks the fastest other clean lap", () => {
    expect(fastestOtherLap(laps, 2)).toBe(3)
    expect(fastestOtherLap(laps, 3)).toBe(2)
  })
  it("falls back to any lap, then null", () => {
    expect(fastestOtherLap(laps.slice(0, 2), 2)).toBe(1)
    expect(fastestOtherLap(laps.slice(1, 2), 2)).toBeNull()
  })
})
