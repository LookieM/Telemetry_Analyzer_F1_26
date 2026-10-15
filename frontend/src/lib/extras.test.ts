import { beforeEach, describe, expect, it, vi } from "vitest"
import type { LapExtra } from "../api/types"
import { loadExtras, saveExtras, usableExtras } from "./extras"

const info: LapExtra[] = [
  { key: "g_lat", label: "Lateral g", unit: "g", per_wheel: false, available: false, reason: "Recorded but empty in this export", channels: ["g_lat"] },
  { key: "g_long", label: "Longitudinal g", unit: "g", per_wheel: false, available: true, reason: null, channels: ["g_long"] },
  { key: "slip_ratio", label: "Slip ratio", unit: "", per_wheel: true, available: true, reason: null, channels: [] },
]

describe("extras selection", () => {
  beforeEach(() => {
    const store = new Map<string, string>()
    vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) })
  })
  it("keeps only picked, available extras (and none before availability is known)", () => {
    expect(usableExtras(["g_lat", "g_long", "slip_ratio", "nope"], info)).toEqual(["g_long", "slip_ratio"])
    expect(usableExtras(["g_long"], undefined)).toEqual([])
  })
  it("remembers the choice per browser and survives bad storage", () => {
    expect(loadExtras()).toEqual([])
    saveExtras(["g_long"])
    expect(loadExtras()).toEqual(["g_long"])
    localStorage.setItem("telemetria.lapExtras", "{oops")
    expect(loadExtras()).toEqual([])
  })
})
