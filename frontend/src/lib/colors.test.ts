import { describe, expect, it } from "vitest"
import { hexToRgb, scaleColor, scaleGradient, tempColor, type Scale } from "./colors"

const SCALE: Scale = [
  [0, "#000000"],
  [0.5, "#ff0000"],
  [1, "#ffffff"],
]

describe("scaleColor", () => {
  it("returns the stop colours at the ends and the middle", () => {
    expect(scaleColor(SCALE, 0)).toBe("rgb(0,0,0)")
    expect(scaleColor(SCALE, 0.5)).toBe("rgb(255,0,0)")
    expect(scaleColor(SCALE, 1)).toBe("rgb(255,255,255)")
  })
  it("interpolates between stops", () => {
    expect(scaleColor(SCALE, 0.25)).toBe("rgb(128,0,0)")
    expect(scaleColor(SCALE, 0.75)).toBe("rgb(255,128,128)")
  })
  it("clamps and rejects non-finite input", () => {
    expect(scaleColor(SCALE, -3)).toBe("rgb(0,0,0)")
    expect(scaleColor(SCALE, 9)).toBe("rgb(255,255,255)")
    expect(scaleColor(SCALE, NaN)).toBeNull()
  })
})

describe("helpers", () => {
  it("parses short and long hex", () => {
    expect(hexToRgb("#fff")).toEqual([255, 255, 255])
    expect(hexToRgb("#2B4C7E")).toEqual([43, 76, 126])
  })
  it("builds a css gradient", () => {
    expect(scaleGradient(SCALE)).toBe("linear-gradient(90deg, #000000 0%, #ff0000 50%, #ffffff 100%)")
  })
  it("colours tyre temperatures against the window", () => {
    expect(tempColor(80, 90, 105)).toBe("#3E7CC9")
    expect(tempColor(95, 90, 105)).toBe("#2E9E44")
    expect(tempColor(110, 90, 105)).toBe("#D7263D")
    expect(tempColor(null, 90, 105)).toBe("#8A9099")
  })
})
