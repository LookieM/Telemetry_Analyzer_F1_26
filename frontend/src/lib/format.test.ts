import { describe, expect, it } from "vitest"
import { fmt, fmtSigned, formatBytes, formatDate, formatLapTime, formatRaceTime, windowsText } from "./format"

describe("lap and race time", () => {
  it("formats lap times like the Streamlit app", () => {
    expect(formatLapTime(66.154)).toBe("1:06.154")
    expect(formatLapTime(59.8421)).toBe("59.842s")
    expect(formatLapTime(125.0)).toBe("2:05.000")
    expect(formatLapTime(60)).toBe("1:00.000")
  })
  it("returns a dash for missing values", () => {
    expect(formatLapTime(null)).toBe("—")
    expect(formatLapTime(NaN)).toBe("—")
    expect(formatRaceTime(undefined)).toBe("—")
  })
  it("formats race times with hours when needed", () => {
    expect(formatRaceTime(2538.563)).toBe("42:18.563")
    expect(formatRaceTime(3723.25)).toBe("1:02:03.250")
    expect(formatRaceTime(5)).toBe("0:05.000")
  })
})

describe("numbers", () => {
  it("fmt handles decimals and null", () => {
    expect(fmt(3.14159, 2)).toBe("3.14")
    expect(fmt(null)).toBe("—")
    expect(fmt(Infinity)).toBe("—")
  })
  it("fmtSigned always shows the sign of non-zero values", () => {
    expect(fmtSigned(0.1234, 3)).toBe("+0.123")
    expect(fmtSigned(-1.5, 1)).toBe("-1.5")
    expect(fmtSigned(0.0001, 2)).toBe("0.00")
    expect(fmtSigned(null)).toBe("—")
  })
  it("formats bytes and dates", () => {
    expect(formatBytes(512)).toBe("512 B")
    expect(formatBytes(71_590_704)).toBe("68.3 MB")
    expect(formatBytes(null)).toBe("—")
    expect(formatDate("2026-10-09T13:24:20+00:00")).toBe("2026-10-09")
  })
})

describe("windowsText", () => {
  it("prints the stop lap with its window", () => {
    expect(windowsText([8, 22], [[7, 9], [22, 22]])).toBe("L8 (7–9), L22")
  })
  it("says no stop for an empty list", () => {
    expect(windowsText([], [])).toBe("no stop")
  })
})
