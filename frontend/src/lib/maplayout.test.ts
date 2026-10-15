import { describe, expect, it } from "vitest"
import type { MapPayload } from "../api/types"
import { nearestOnScreen, projectTrack, zoomMapPayload } from "./maplayout"

describe("projectTrack", () => {
  const x = [0, 100, 100, 0]
  const y = [0, 0, 50, 50]

  it("fits the line inside the padded canvas and flips Y", () => {
    const p = projectTrack(x, y, null, 300, 200, 20)
    // scale limited by width: (300-40)/100 = 2.6 -> height 130, centred vertically
    expect(p.px[0]).toBeCloseTo(20)
    expect(p.px[1]).toBeCloseTo(280)
    expect(p.py[0]).toBeGreaterThan(p.py[2]) // world y up -> canvas y down
    expect(p.py[0] - p.py[2]).toBeCloseTo(130)
    expect((p.py[0] + p.py[2]) / 2).toBeCloseTo(100)
  })

  it("includes the outline in the bounds and skips nulls", () => {
    const p = projectTrack([0, null, 10], [0, 5, 10], { x: [-10, 20], y: [-10, 20] }, 100, 100, 0)
    expect(Number.isNaN(p.px[1])).toBe(true)
    expect(p.ox).toHaveLength(2)
    expect(p.ox[0]).toBeCloseTo(0)
    expect(p.ox[1]).toBeCloseTo(100)
  })

  it("returns empty arrays when there are no finite points", () => {
    expect(projectTrack([null], [null], null, 100, 100)).toEqual({ px: [], py: [], ox: [], oy: [] })
  })
})

describe("nearestOnScreen", () => {
  const px = [10, 50, 90]
  const py = [10, 10, 10]
  it("returns the closest point within the radius", () => {
    expect(nearestOnScreen(px, py, 52, 14)).toBe(1)
    expect(nearestOnScreen(px, py, 88, 0)).toBe(2)
  })
  it("returns null when the pointer is too far", () => {
    expect(nearestOnScreen(px, py, 50, 200)).toBeNull()
    expect(nearestOnScreen([], [], 0, 0)).toBeNull()
  })
})

describe("zoomMapPayload", () => {
  const base = {
    x: [0, 1, 2, 3, 4],
    y: [0, 0, 1, 1, 2],
    d: [0, 100, 200, 300, 400],
    channels: [{ label: "Speed", unit: "km/h", decimals: 0, values: [10, 11, 12, 13, 14], ref: [20, 21, 22, 23, 24] }],
    cmp_label: "L1",
    ref_label: "L2",
    color: { values: [1, 2, 3, 4, 5], min: 1, max: 5, scale: [], label: "Speed", decimals: 0 },
    labels: [{ text: "T1", d: 50 }, { text: "T2", d: 350 }],
    spans: [{ from: 0, to: 120, name: "T1" }, { from: 330, to: 400, name: "T2" }],
    outline: { x: [0, 9], y: [0, 9] },
    session_id: 1,
    lap: 1,
    ref_lap: null,
    ref_session: null,
    track: "Monza",
    track_length: 400,
  } as unknown as MapPayload
  it("keeps only the samples, labels and spans inside the window and drops the outline", () => {
    const z = zoomMapPayload(base, [90, 310])
    expect(z.d).toEqual([100, 200, 300])
    expect(z.x).toEqual([1, 2, 3])
    expect(z.channels[0].values).toEqual([11, 12, 13])
    expect(z.channels[0].ref).toEqual([21, 22, 23])
    expect(z.color?.values).toEqual([2, 3, 4])
    expect(z.labels).toEqual([])
    expect(z.spans.map((s) => s.name)).toEqual(["T1"])
    expect(z.outline).toBeNull()
  })
  it("returns the payload unchanged when the window holds fewer than two samples", () => {
    expect(zoomMapPayload(base, [101, 150])).toBe(base)
  })
})
