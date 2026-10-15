import { describe, expect, it } from "vitest"
import type { CornerMetrics, CornerReportRow, CornersPayload } from "../api/types"
import { biggestLoss, buildCornerRows, cornerAt, cornerMarkers, lossKind, sortRows, zoomRange } from "./corners"

const metrics = (o: Partial<CornerMetrics> = {}): CornerMetrics => ({
  time_s: null,
  entry_kmh: null,
  vmin_kmh: null,
  exit_kmh: null,
  brake_m: null,
  trail_m: null,
  trail_s: null,
  throttle_m: null,
  ...o,
})

function corner(id: number, start: number, end: number, delta: Partial<CornerMetrics>, focus: Partial<CornerMetrics> = {}, merged: number[] = []): CornerReportRow {
  return {
    id,
    name: `T${id}`,
    start_m: start,
    end_m: end,
    apex_m: (start + end) / 2,
    vmin_kmh: 100,
    speed_class: "slow",
    merged_from: merged,
    focus: metrics({ time_s: 4, vmin_kmh: 98, ...focus }),
    ref: metrics({ time_s: 3.9, brake_m: start + 5, throttle_m: end - 3 }),
    delta: metrics(delta),
    phases: { entry: [start, start + 50], mid: [start + 50, start + 80], exit: [start + 80, end] },
    callouts: [],
  }
}

const payload: CornersPayload = {
  track: "Monza",
  session_id: 1,
  lap: 5,
  reference: { session: 1, lap: 3 },
  corners_source: { session: 1, lap: 3, built_at: "2026-01-01" },
  corners: [
    corner(1, 100, 300, { time_s: 0.12, brake_m: -12 }, { brake_m: 93, throttle_m: 297 }),
    corner(2, 500, 700, { time_s: -0.08 }, {}, [550, 650]),
    corner(3, 900, 1000, { time_s: 0.01, vmin_kmh: null }),
  ],
  lap_delta: 0.2,
  sum_corner_delta: 0.05,
  straights_delta: 0.15,
  start_delta: 0,
}

describe("buildCornerRows", () => {
  const rows = buildCornerRows(payload)
  it("keeps order and names and flags complexes", () => {
    expect(rows.map((r) => [r.order, r.name, r.complex])).toEqual([
      [1, "T1", false],
      [2, "T2", true],
      [3, "T3", false],
    ])
  })
  it("carries focus values with their differences", () => {
    expect(rows[0]).toMatchObject({ time: 4, timeDelta: 0.12, vmin: 98, brake: 93, brakeDelta: -12 })
    expect(rows[2].vminDelta).toBeNull()
  })
})

describe("sortRows", () => {
  const rows = buildCornerRows(payload)
  it("sorts by time loss, biggest first", () => {
    expect(sortRows(rows, "timeDelta", "desc").map((r) => r.name)).toEqual(["T1", "T3", "T2"])
  })
  it("puts missing values last in both directions", () => {
    expect(sortRows(rows, "brake", "asc").map((r) => r.name)).toEqual(["T1", "T2", "T3"])
    expect(sortRows(rows, "brake", "desc").map((r) => r.name)).toEqual(["T1", "T2", "T3"])
  })
  it("returns a copy in lap order for the default key", () => {
    const shuffled = [rows[2], rows[0], rows[1]]
    expect(sortRows(shuffled, "order", "asc").map((r) => r.name)).toEqual(["T1", "T2", "T3"])
    expect(shuffled[0].name).toBe("T3")
  })
})

describe("zoomRange", () => {
  it("adds the margin and stays inside the lap", () => {
    expect(zoomRange({ startM: 500, endM: 700 }, 5000, 60)).toEqual([440, 760])
    expect(zoomRange({ startM: 20, endM: 4990 }, 5000, 60)).toEqual([0, 5000])
    expect(zoomRange({ startM: 20, endM: 100 }, null, 60)).toEqual([0, 160])
  })
})

describe("lossKind", () => {
  it("colours only differences above the noise", () => {
    expect(lossKind(0.12)).toBe("loss")
    expect(lossKind(-0.08)).toBe("gain")
    expect(lossKind(0.029)).toBe("flat")
    expect(lossKind(null)).toBe("flat")
  })
})

describe("markers and lookups", () => {
  const rows = buildCornerRows(payload)
  it("marks the focus and reference brake and throttle points that exist", () => {
    expect(cornerMarkers(rows[0]).map((m) => [m.label, m.x])).toEqual([
      ["Brake", 93],
      ["Full throttle", 297],
      ["Brake (ref)", 105],
      ["Full thr (ref)", 297],
    ])
    expect(cornerMarkers({ ...rows[0], points: { brake: null, throttle: null, refBrake: null, refThrottle: null } })).toEqual([])
  })
  it("finds the biggest loss above the noise", () => {
    expect(biggestLoss(rows)?.name).toBe("T1")
    expect(biggestLoss(rows.filter((r) => r.name !== "T1"))).toBeNull()
  })
  it("names the corner under a distance", () => {
    expect(cornerAt(rows, 550)).toBe("T2")
    expect(cornerAt(rows, 400)).toBeNull()
    expect(cornerAt(rows, null)).toBeNull()
  })
})
