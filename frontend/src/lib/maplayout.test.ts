import { describe, expect, it } from "vitest"
import { nearestOnScreen, projectTrack } from "./maplayout"

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
