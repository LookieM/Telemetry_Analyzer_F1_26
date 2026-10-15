import { describe, expect, it } from "vitest"
import type { ChannelsPayload, ComparePayload, InventoryRow, OptimisePayload, ReviewJson, TyresPayload } from "../api/types"
import { WHEEL_COLORS } from "./colors"
import {
  PA_PER_PSI,
  compareTrace,
  cornerBands,
  driverTrace,
  masked,
  raceTrace,
  scaled,
  stintSegments,
  stintTrace,
  tyreLapColumns,
  tyreLapTrace,
  wheelColumnsFor,
} from "./traces"

const labels = { cmp: "L10", ref: "L11" }

describe("series helpers", () => {
  it("scales values and keeps nulls", () => {
    expect(scaled([0.5, null, 1], 100)).toEqual([50, null, 100])
    expect(scaled(undefined, 2)).toEqual([])
  })
  it("masks values", () => {
    expect(masked([1, 2, 3], [true, false, true])).toEqual([1, null, 3])
  })
  it("turns corner spans into labelled bands", () => {
    expect(cornerBands([{ from: 10, to: 50, name: "T1" }])).toEqual([{ from: 10, to: 50, label: "T1" }])
    expect(cornerBands(undefined)).toEqual([])
  })
})

describe("driver traces", () => {
  const ch: ChannelsPayload = {
    session_id: 1,
    lap: 10,
    x: [0, 2, 4],
    x_label: "Distance (m)",
    channels: { speed: [100, 200, 300], throttle: [0, 0.5, 1], brake: [1, 0, 0], gear: [2, 3, 4], rpm: [1, 2, 3], steering: [0, 0.1, -0.1], lap_time: [0, 1, 2] },
    units: {},
  }
  it("builds speed, throttle/brake, gear and steering panes with percentages", () => {
    const t = driverTrace(ch, labels)
    expect(t.x).toEqual([0, 2, 4])
    expect(t.panes.map((p) => p.title)).toEqual(["Speed", "Throttle / Brake", "Gear", "Steering"])
    const tb = t.panes[1]
    expect(tb.range).toEqual([-2, 102])
    expect(tb.series.map((s) => s.label)).toEqual(["Thr L10", "Brk L10"])
    expect(tb.series[0].values).toEqual([0, 50, 100])
    expect(t.panes[2].series[0].mode).toBe("step")
  })
  it("adds the reference series and a delta pane for comparisons", () => {
    const cmp = {
      session_id: 1,
      lap: 10,
      ref_session: 1,
      ref_lap: 11,
      lap_distance: [0, 1, 2],
      delta_time: [0, 0.01, 0.02],
      final_delta: 0.02,
      sectors: [],
      mini_sectors: [],
      cmp_speed: [1, 2, 3],
      ref_speed: [1, 2, 4],
      cmp_throttle: [1, 1, 1],
      ref_throttle: [0, 0, 0],
      cmp_brake: [0, 0, 0],
      ref_brake: [0, 0, 0],
      cmp_gear: [3, 3, 3],
      ref_gear: [3, 3, 3],
      cmp_steering: [0, 0, 0],
      ref_steering: [0, 0, 0],
    } as ComparePayload
    const t = compareTrace(cmp, labels)
    expect(t.panes.map((p) => p.title)).toEqual(["Speed", "Δt L10 − L11", "Throttle / Brake", "Gear", "Steering"])
    expect(t.panes[0].series.map((s) => [s.label, s.dash ?? false])).toEqual([
      ["Speed L10", false],
      ["Speed L11", true],
    ])
    expect(t.panes[1].series[0].values).toEqual([0, 0.01, 0.02])
    expect(t.panes[2].series[1].values).toEqual([0, 0, 0])
    expect(t.x).toEqual([0, 1, 2])
  })
})

describe("tyre lap trace", () => {
  const inv: InventoryRow[] = [
    { Group: "Tyres", Channel: "Tyre temp (export)", Unit: "C", Columns: "tyre_temp_0, tyre_temp_1, tyre_temp_2, tyre_temp_3" },
    { Group: "Tyres", Channel: "Tyre inner temp", Unit: "C", Columns: "tyre_tempInternalAir_0, tyre_tempInternalAir_1, tyre_tempInternalAir_2, tyre_tempInternalAir_3" },
    { Group: "Tyres", Channel: "Tyre pressure", Unit: "Pa", Columns: "tyre_press_0, tyre_press_1, tyre_press_2, tyre_press_3" },
    { Group: "Tyres", Channel: "Tyre wear", Unit: "0-1", Columns: "tyre_wear_0, tyre_wear_1, tyre_wear_2, tyre_wear_3" },
    { Group: "Unregistered", Channel: "slip_max", Unit: "", Columns: "slip_max" },
  ]
  it("reads wheel columns from the inventory", () => {
    expect(wheelColumnsFor(inv, "Tyre pressure")).toEqual(["tyre_press_0", "tyre_press_1", "tyre_press_2", "tyre_press_3"])
    expect(wheelColumnsFor(inv, "Brake temp")).toBeNull()
    expect(wheelColumnsFor(undefined, "x")).toBeNull()
  })
  it("prefers inner temperature and shows the export channel as surface", () => {
    const cols = tyreLapColumns(inv)
    expect(cols.temp?.label).toBe("Tyre inner temp")
    expect(cols.surface?.[0]).toBe("tyre_temp_0")
    expect(cols.all).toContain("slip_max")
    expect(cols.all).toContain("speed")
    expect(cols.all).toHaveLength(4 + 4 + 4 + 4 + 1 + 1)
  })
  it("does not repeat the temperature channel as surface when it is the only one", () => {
    const cols = tyreLapColumns([inv[0]])
    expect(cols.temp?.label).toBe("Tyre temp (export)")
    expect(cols.surface).toBeNull()
  })
  it("converts pressure to psi, wear to percent and draws the window", () => {
    const cols = tyreLapColumns(inv)
    const ch: ChannelsPayload = { session_id: 1, lap: 1, x: [0, 1], x_label: "", units: {}, channels: { speed: [100, 120], slip_max: [0.1, 0.2] } }
    for (const c of cols.all) ch.channels[c] ??= [PA_PER_PSI * 22, PA_PER_PSI * 23]
    ch.channels["tyre_wear_0"] = [0.1, 0.2]
    const t = tyreLapTrace(ch, cols, { lo: 90, hi: 105 })
    const temp = t.panes[0]
    expect(temp.series.map((s) => s.label)).toEqual(["FL", "FR", "RL", "RR", "window lo", "window hi"])
    expect(temp.series[4].values).toEqual([90, 90])
    const press = t.panes.find((p) => p.title === "Hot pressure")!
    expect(press.series[0].values[0]).toBeCloseTo(22, 6)
    expect(press.series[0].color).toBe(WHEEL_COLORS.FL)
    const wear = t.panes.find((p) => p.title === "Wear")!
    expect(wear.series[0].values).toEqual([10, 20])
    expect(t.panes[t.panes.length - 1].title).toBe("Speed")
  })
})

function tyresPayload(): TyresPayload {
  const mkRow = (lap: number, cls: string, age: number, t: number) => ({
    lap,
    lap_class: cls,
    stint: lap < 3 ? 1 : 2,
    age,
    compound: 16,
    lap_time: 70 + t,
    fuel_start: 30,
    corr_time: 70 + t,
    W_FL: lap * 3,
    W_FR: lap * 3,
    W_RL: lap * 3,
    W_RR: lap * 3,
    T_FL: 90,
    T_FR: 90,
    T_RL: 90,
    T_RR: 90,
    P_FL: 22,
    P_FR: 22,
    P_RL: 22,
    P_RR: 22,
  })
  const summary = (idx: number, laps: number[], color: string) => ({
    stint: { idx, laps, compound: 16, push_laps: laps, ages: {} },
    deg: { slope: 0.1, intercept: 70, r2: 0.9, n: laps.length, cliff_age: null },
    wear_rate: {},
    limiting_wheel: "FL",
    wear_now: 10,
    laps_to_limit: 5,
    temp_mean: {},
    temp_in_window: {},
    hot_psi: {},
    cold_psi: {},
    warmup_s: 0,
    fuel_per_lap: 0.8,
    label: "C5 (S)",
    role: idx === 1 ? "H" : "S",
    color,
    targets: { compound: 16, temp_lo: 90, temp_hi: 105, hot_front_psi: null, hot_rear_psi: null, source: "default" },
    pressure: [],
  })
  return {
    session_id: 1,
    track: "Spielberg",
    state: "dry",
    wear_limit: 66,
    temp_channel: "Tyre inner temp",
    temp_kind: "inner",
    stints: [summary(0, [1, 2], "#D7263D"), summary(1, [3, 4], "#8A9099")],
    wheel_table: [mkRow(0, "start", 0, 3), mkRow(1, "push", 1, 0.5), mkRow(2, "pit", 2, 20), mkRow(3, "push", 0, 0.1), mkRow(4, "push", 1, 0.2)],
    targets: {},
    allocation: {},
    race_stats: { fuel_s_per_kg: 0.03, fuel_pairs: 0, box_wear_pct: 66, n_stops: 1 },
  }
}

describe("stint trace", () => {
  it("builds pace, wear, temp and pressure panes with stint bands and pit markers", () => {
    const t = stintTrace(tyresPayload())
    expect(t.xLabel).toBe("Lap")
    expect(t.x).toEqual([0, 1, 2, 3, 4])
    expect(t.panes.map((p) => p.title)).toEqual(["Lap time, fuel-corrected to 5 kg", "Wear (end of lap)", "Tyre temp (lap mean)", "Hot pressure (lap median)"])
    expect(t.bands).toEqual([
      { from: 0.5, to: 2.5, label: "S1 C5 (S)", color: "#D7263D" },
      { from: 2.5, to: 4.5, label: "S2 C5 (S)", color: "#8A9099" },
    ])
    expect(t.markers).toEqual([{ x: 2, label: "PIT" }])
  })
  it("keeps non-push laps out of the stint series and the trend fit", () => {
    const pace = stintTrace(tyresPayload()).panes[0]
    const other = pace.series[0]
    expect(other.label).toBe("other laps")
    expect(other.values).toEqual([73, null, 90, null, null])
    const s1 = pace.series[1]
    expect(s1.values).toEqual([null, 70.5, null, null, null])
    const trend = pace.series[2]
    expect(trend.label).toBe("S1 trend +0.100s/lap")
    expect(trend.values).toEqual([null, 70.1, 70.2, null, null])
    // axis range follows push laps only
    expect(pace.range?.[0]).toBeCloseTo(70.1 - 0.5)
    expect(pace.range?.[1]).toBeCloseTo(70.5 + 0.8)
  })
  it("builds timeline segments with the hard compound marked light", () => {
    const seg = stintSegments(tyresPayload().stints)
    expect(seg[0]).toMatchObject({ from: 1, to: 2, text: "S", light: false })
    expect(seg[1]).toMatchObject({ from: 3, to: 4, text: "H", light: true, title: "C5 (S) · L3–4" })
  })
  it("returns an empty chart without lap rows", () => {
    expect(stintTrace({ ...tyresPayload(), wheel_table: [] })).toEqual({ x: [], panes: [] })
  })
})

describe("race trace", () => {
  const opt = {
    race_trace: {
      laps: [1, 2, 3],
      box_laps: [2],
      plans: [
        { label: "A", lap_times: [70, 90, 70], gap_to_best: [0, 0, 0] },
        { label: "B", lap_times: [71, 89, 71], gap_to_best: [1, 0, 1] },
      ],
    },
  } as unknown as OptimisePayload
  it("returns null without a trace", () => {
    expect(raceTrace({ ...opt, race_trace: null }, null)).toBeNull()
  })
  it("builds gap and lap time panes with box markers", () => {
    const t = raceTrace(opt, null)!
    expect(t.x).toEqual([1, 2, 3])
    expect(t.markers).toEqual([{ x: 2, label: "box" }])
    expect(t.panes).toHaveLength(2)
    expect(t.panes[0].series.map((s) => s.label)).toEqual(["A", "B"])
  })
  it("adds the actual race as a cumulative gap to the best plan", () => {
    const review = { actual_lap_times: [72, 90, 70, 99] } as unknown as ReviewJson
    const t = raceTrace(opt, review)!
    const actualGap = t.panes[0].series[2]
    expect(actualGap.label).toBe("Actual")
    expect(actualGap.values).toEqual([2, 2, 2])
    const actualTimes = t.panes[1].series[2]
    expect(actualTimes.values).toEqual([72, 90, 70]) // trimmed to the race length
    expect(actualTimes.mode).toBe("points")
  })
})
