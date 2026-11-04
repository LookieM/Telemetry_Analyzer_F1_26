/** Turn API payloads into TraceChart data (panes / series / bands / markers). Pure, no React. */
import type {
  ChannelsPayload,
  ComparePayload,
  InventoryRow,
  LapSummary,
  OptimisePayload,
  ReviewJson,
  Series,
  StintSummary,
  TyresPayload,
  WheelRow,
} from "../api/types"
import { BRAKE, DELTA, FOCUS, GEAR, NEUTRAL, PLAN_COLORS, REF, THROTTLE, WHEELS, WHEEL_COLORS } from "./colors"

export interface SeriesSpec {
  label: string
  values: Series
  color?: string
  dash?: boolean
  width?: number
  decimals?: number
  mode?: "points" | "step"
  size?: number
  hollow?: boolean
}

export interface PaneSpec {
  title: string
  unit?: string
  series: SeriesSpec[]
  height?: number
  range?: [number, number]
  decimals?: number
  axisDecimals?: number
}

export interface Band {
  from: number
  to: number
  label?: string
  color?: string
}

export interface Marker {
  x: number
  label?: string
  color?: string
}

export interface TraceData {
  x: number[]
  panes: PaneSpec[]
  xLabel?: string
  xDecimals?: number
  bands?: Band[]
  markers?: Marker[]
  emptyText?: string
}

export const PA_PER_PSI = 6894.757

/** Multiply every finite value (null stays null). */
export function scaled(values: Series | undefined, mult: number): Series {
  return (values ?? []).map((v) => (v == null ? null : v * mult))
}

/** Keep values where mask is true, null elsewhere. */
export function masked(values: Series, mask: boolean[]): Series {
  return values.map((v, i) => (mask[i] ? v : null))
}

export function constant(n: number, v: number): Series {
  return Array.from({ length: n }, () => v)
}

export function cornerBands(spans: { from: number; to: number; name: string }[] | undefined): Band[] {
  return (spans ?? []).map((s) => ({ from: s.from, to: s.to, label: s.name }))
}

interface Labels {
  cmp: string
  ref: string
}

function pair(
  focus: Series,
  ref: Series | undefined,
  title: string,
  labels: Labels,
  o: { mult?: number; color?: string; refColor?: string; mode?: "step" } = {},
): SeriesSpec[] {
  const mult = o.mult ?? 1
  const out: SeriesSpec[] = [{ label: `${title} ${labels.cmp}`, values: scaled(focus, mult), color: o.color ?? FOCUS, mode: o.mode }]
  if (ref) out.push({ label: `${title} ${labels.ref}`, values: scaled(ref, mult), color: o.refColor ?? REF, dash: true, mode: o.mode })
  return out
}

/** Driver panes: speed, [Δt], throttle / brake, gear, steering. `ref` series are optional. */
function driverPanes(
  get: (name: string) => { focus: Series; ref?: Series },
  delta: Series | null,
  labels: Labels,
  paneHeight: number,
): PaneSpec[] {
  const speed = get("speed")
  const thr = get("throttle")
  const brk = get("brake")
  const gear = get("gear")
  const steer = get("steering")
  const panes: PaneSpec[] = [{ title: "Speed", unit: "km/h", height: paneHeight + 40, decimals: 0, series: pair(speed.focus, speed.ref, "Speed", labels) }]
  if (delta) {
    panes.push({
      title: `Δt ${labels.cmp} − ${labels.ref}`,
      unit: "s",
      height: paneHeight - 20,
      decimals: 3,
      axisDecimals: 2,
      series: [{ label: "Δt", values: delta, color: DELTA, width: 2 }],
    })
  }
  panes.push({
    title: "Throttle / Brake",
    unit: "%",
    height: paneHeight,
    decimals: 0,
    range: [-2, 102],
    series: [
      ...pair(thr.focus, thr.ref, "Thr", labels, { mult: 100, color: THROTTLE, refColor: THROTTLE }),
      ...pair(brk.focus, brk.ref, "Brk", labels, { mult: 100, color: BRAKE, refColor: BRAKE }),
    ],
  })
  panes.push({
    title: "Gear",
    height: paneHeight - 30,
    decimals: 0,
    series: pair(gear.focus, gear.ref, "Gear", labels, { color: GEAR, refColor: NEUTRAL, mode: "step" }),
  })
  panes.push({ title: "Steering", height: paneHeight - 20, decimals: 2, axisDecimals: 1, series: pair(steer.focus, steer.ref, "Steer", labels) })
  return panes
}

export const TRACE_CHANNELS = ["speed", "throttle", "brake", "gear", "rpm", "steering", "lap_time"]

// ---------------------------------------------------------------- optional extra panes

export interface ExtraPaneDef {
  key: string
  title: string
  unit: string
  perWheel: boolean
  mult: number
  decimals: number
  height: number
}

/** Optional lap-trace panes (keys match the API's `extras`); per-wheel payload names are `<key>_FL` ... `<key>_RR`. */
export const EXTRA_PANES: ExtraPaneDef[] = [
  { key: "g_lat", title: "Lateral g", unit: "g", perWheel: false, mult: 1, decimals: 2, height: 120 },
  { key: "g_long", title: "Longitudinal g", unit: "g", perWheel: false, mult: 1, decimals: 2, height: 120 },
  { key: "slip_angle", title: "Slip angle", unit: "°", perWheel: true, mult: 180 / Math.PI, decimals: 1, height: 140 },
  { key: "slip_ratio", title: "Slip ratio", unit: "", perWheel: true, mult: 1, decimals: 3, height: 140 },
  { key: "tyre_surface", title: "Tyre surface temp", unit: "°C", perWheel: true, mult: 1, decimals: 0, height: 140 },
  { key: "tyre_inner", title: "Tyre inner temp", unit: "°C", perWheel: true, mult: 1, decimals: 0, height: 140 },
]

const hasData = (v: Series | undefined) => !!v && v.some((x) => x != null)

/** Panes for the chosen extras. g panes overlay focus vs reference; per-wheel panes show four wheels (reference dashed, thin). */
export function extraPanes(get: (name: string) => { focus: Series; ref?: Series }, keys: string[] | undefined, labels: Labels): PaneSpec[] {
  const panes: PaneSpec[] = []
  for (const def of EXTRA_PANES) {
    if (!keys?.includes(def.key)) continue
    let series: SeriesSpec[]
    if (def.perWheel) {
      series = []
      for (const w of WHEELS) {
        const { focus, ref } = get(`${def.key}_${w}`)
        const color = WHEEL_COLORS[w]
        series.push({ label: w, values: scaled(focus, def.mult), color, decimals: def.decimals })
        if (hasData(ref)) series.push({ label: `${w} ${labels.ref}`, values: scaled(ref, def.mult), color, dash: true, width: 1, decimals: def.decimals })
      }
    } else {
      const { focus, ref } = get(def.key)
      series = pair(focus, hasData(ref) ? ref : undefined, def.title, labels, { mult: def.mult })
      series.forEach((s) => (s.decimals = def.decimals))
    }
    if (!series.some((s) => hasData(s.values))) continue
    panes.push({ title: def.title, unit: def.unit, height: def.height, decimals: def.decimals, axisDecimals: def.decimals > 1 ? 1 : def.decimals, series })
  }
  return panes
}

/** Single lap (no reference). */
export function driverTrace(ch: ChannelsPayload, labels: Labels, paneHeight = 130, extras?: string[]): TraceData {
  const panes = driverPanes((n) => ({ focus: ch.channels[n] ?? [] }), null, labels, paneHeight)
  panes.push(...extraPanes((n) => ({ focus: ch.channels[n] ?? [] }), extras, labels))
  return { x: ch.x, panes }
}

/** Focus lap vs reference lap (same or another session) on the aligned 1 m grid. */
export function compareTrace(cmp: ComparePayload, labels: Labels, paneHeight = 130, extras?: string[]): TraceData {
  const col = (k: string) => (cmp[k] as Series | undefined) ?? []
  const panes = driverPanes((n) => ({ focus: col(`cmp_${n}`), ref: col(`ref_${n}`) }), cmp.delta_time, labels, paneHeight)
  panes.push(...extraPanes((n) => ({ focus: col(`cmp_${n}`), ref: col(`ref_${n}`) }), extras, labels))
  return { x: cmp.lap_distance, panes }
}

// ---------------------------------------------------------------- tyres

/** Four per-wheel column names (RL, RR, FL, FR) for an inventory channel label, or null. */
export function wheelColumnsFor(inv: InventoryRow[] | undefined, channel: string): string[] | null {
  const row = inv?.find((r) => r.Channel === channel)
  if (!row) return null
  const cols = row.Columns.split(",").map((c) => c.trim())
  return cols.length === 4 ? cols : null
}

export interface TyreLapColumns {
  temp: { label: string; cols: string[] } | null
  surface: string[] | null
  brakes: string[] | null
  press: string[] | null
  wear: string[] | null
  all: string[]
}

/** Which per-wheel channels to request for the lap trace (mirrors channels.primary_tyre_temp / surface_tyre_temp). */
export function tyreLapColumns(inv: InventoryRow[] | undefined): TyreLapColumns {
  let temp: TyreLapColumns["temp"] = null
  for (const name of ["Tyre inner temp", "Tyre surface temp", "Tyre temp (export)"]) {
    const cols = wheelColumnsFor(inv, name)
    if (cols) {
      temp = { label: name, cols }
      break
    }
  }
  const surface = wheelColumnsFor(inv, "Tyre surface temp") ?? wheelColumnsFor(inv, "Tyre temp (export)")
  const brakes = wheelColumnsFor(inv, "Brake temp")
  const press = wheelColumnsFor(inv, "Tyre pressure")
  const wear = wheelColumnsFor(inv, "Tyre wear")
  const hasSlip = !!inv?.some((r) => r.Columns === "slip_max")
  const showSurface = surface && !(temp && temp.cols[0] === surface[0]) ? surface : null
  const all = [...(temp?.cols ?? []), ...(showSurface ?? []), ...(brakes ?? []), ...(press ?? []), ...(wear ?? []), ...(hasSlip ? ["slip_max"] : []), "speed"]
  return { temp, surface: showSurface, brakes, press, wear, all }
}

function wheelSeries(ch: ChannelsPayload, cols: string[], mult = 1, decimals?: number): SeriesSpec[] {
  return cols.map((c, i) => ({ label: WHEELS[i], values: scaled(ch.channels[c], mult), color: WHEEL_COLORS[WHEELS[i]], decimals }))
}

export function tyreLapTrace(ch: ChannelsPayload, cols: TyreLapColumns, window: { lo: number; hi: number } | null): TraceData {
  const n = ch.x.length
  const panes: PaneSpec[] = []
  if (cols.temp) {
    const lines = wheelSeries(ch, cols.temp.cols)
    if (window) {
      lines.push({ label: "window lo", values: constant(n, window.lo), color: NEUTRAL, dash: true, width: 1 })
      lines.push({ label: "window hi", values: constant(n, window.hi), color: NEUTRAL, dash: true, width: 1 })
    }
    panes.push({ title: cols.temp.label, unit: "°C", height: 170, decimals: 0, series: lines })
  }
  if (cols.surface) panes.push({ title: "Tyre surface temp", unit: "°C", height: 120, decimals: 0, series: wheelSeries(ch, cols.surface) })
  if (cols.brakes) panes.push({ title: "Brake temp", unit: "°C", height: 110, decimals: 0, series: wheelSeries(ch, cols.brakes) })
  if (cols.press)
    panes.push({ title: "Hot pressure", unit: "psi", height: 130, decimals: 2, axisDecimals: 1, series: wheelSeries(ch, cols.press, 1 / PA_PER_PSI, 2) })
  if (cols.wear) panes.push({ title: "Wear", unit: "%", height: 110, decimals: 1, series: wheelSeries(ch, cols.wear, 100) })
  if (ch.channels["slip_max"])
    panes.push({
      title: "Max wheel slip",
      height: 90,
      decimals: 3,
      axisDecimals: 2,
      series: [{ label: "slip", values: ch.channels["slip_max"], color: BRAKE, decimals: 3 }],
    })
  panes.push({ title: "Speed", unit: "km/h", height: 90, decimals: 0, series: [{ label: "Speed", values: ch.channels["speed"] ?? [], color: FOCUS }] })
  return { x: ch.x, panes, emptyText: panes.length <= 1 ? "No tyre channels on this lap." : undefined }
}

function column(rows: WheelRow[], key: string): Series {
  return rows.map((r) => {
    const v = r[key]
    return typeof v === "number" && Number.isFinite(v) ? v : null
  })
}

/** Lap-by-lap stint view: fuel-corrected pace with stint fits, wear, temps, pressures. */
export function stintTrace(tyres: TyresPayload): TraceData {
  const rows = tyres.wheel_table
  if (!rows.length) return { x: [], panes: [] }
  const laps = rows.map((r) => r.lap)
  const push = rows.map((r) => r.lap_class === "push")
  const corr = column(rows, "corr_time")
  const paceLines: SeriesSpec[] = [
    { label: "other laps", values: masked(corr, push.map((p) => !p)), color: NEUTRAL, mode: "points", size: 6, hollow: true, decimals: 3 },
  ]
  const bands: Band[] = []
  for (const s of tyres.stints) {
    const lapsSet = new Set(s.stint.laps)
    const inStint = rows.map((r) => lapsSet.has(r.lap))
    const tag = `S${s.stint.idx + 1}`
    paceLines.push({
      label: `${tag} ${s.label}`,
      values: masked(corr, inStint.map((v, i) => v && push[i])),
      color: s.color,
      mode: "points",
      size: 7,
      decimals: 3,
    })
    if (s.deg.slope != null && s.deg.intercept != null) {
      const { slope, intercept } = s.deg
      paceLines.push({
        label: `${tag} trend ${slope >= 0 ? "+" : ""}${slope.toFixed(3)}s/lap`,
        values: rows.map((r, i) => (inStint[i] ? intercept + slope * r.age : null)),
        color: s.color,
        dash: true,
        decimals: 3,
      })
    }
    bands.push({ from: s.stint.laps[0] - 0.5, to: s.stint.laps[s.stint.laps.length - 1] + 0.5, label: `${tag} ${s.label}`, color: s.color })
  }
  const pushCorr = corr.filter((v, i): v is number => push[i] && v != null)
  const range: [number, number] | undefined = pushCorr.length ? [Math.min(...pushCorr) - 0.5, Math.max(...pushCorr) + 0.8] : undefined
  const panes: PaneSpec[] = [{ title: "Lap time, fuel-corrected to 5 kg", unit: "s", height: 200, decimals: 3, axisDecimals: 1, range, series: paceLines }]
  const groups: [string, string, string, number][] = [
    ["W_", "Wear (end of lap)", "%", 1],
    ["T_", "Tyre temp (lap mean)", "°C", 0],
    ["P_", "Hot pressure (lap median)", "psi", 2],
  ]
  for (const [prefix, title, unit, dec] of groups) {
    if (!(`${prefix}FL` in rows[0])) continue
    panes.push({
      title,
      unit,
      height: 120,
      decimals: dec,
      axisDecimals: dec === 0 ? 0 : 1,
      series: WHEELS.map((w) => ({ label: w, values: column(rows, `${prefix}${w}`), color: WHEEL_COLORS[w], decimals: dec })),
    })
  }
  const markers: Marker[] = rows.filter((r) => r.lap_class === "pit").map((r) => ({ x: r.lap, label: "PIT" }))
  return { x: laps, panes, bands, markers, xLabel: "Lap" }
}

export interface StintRow {
  from: number
  to: number
  color: string
  text: string
  title: string
  light?: boolean
}

export function stintSegments(summaries: StintSummary[]): StintRow[] {
  return summaries.map((s) => {
    const a = s.stint.laps[0]
    const b = s.stint.laps[s.stint.laps.length - 1]
    return { from: a, to: b, color: s.color, text: s.role || s.label, title: `${s.label} · L${a}–${b}`, light: s.role === "H" }
  })
}

// ---------------------------------------------------------------- strategy

function finiteValues(arr: Series[]): number[] {
  return arr.flat().filter((v): v is number => v != null && Number.isFinite(v))
}

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return NaN
  const idx = (sorted.length - 1) * p
  const lo = Math.floor(idx)
  const hi = Math.ceil(idx)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo)
}

/** Gap-to-best and lap-time panes for the top plans (+ the plan that was actually run). */
export function raceTrace(opt: OptimisePayload, review: ReviewJson | null): TraceData | null {
  const rt = opt.race_trace
  if (!rt || !rt.plans.length) return null
  const best = rt.plans[0].lap_times
  const gap: SeriesSpec[] = rt.plans.map((p, i) => ({ label: p.label, values: p.gap_to_best, color: PLAN_COLORS[i % PLAN_COLORS.length], decimals: 2 }))
  const times: SeriesSpec[] = rt.plans.map((p, i) => ({ label: p.label, values: p.lap_times, color: PLAN_COLORS[i % PLAN_COLORS.length], decimals: 3 }))
  if (review) {
    // Same indexing as the plan traces: entry i is race lap i + 1.
    const actual = review.actual_lap_times.slice(0, rt.laps.length)
    let cum = 0
    let cumBest = 0
    const gapActual: Series = actual.map((t, i) => {
      cum += t ?? 0
      cumBest += best[i] ?? 0
      return cum - cumBest
    })
    gap.push({ label: "Actual", values: gapActual, color: NEUTRAL, dash: true, decimals: 2 })
    times.push({ label: "Actual", values: actual, color: NEUTRAL, dash: true, decimals: 3, mode: "points", size: 5 })
  }
  const sorted = finiteValues(times.map((t) => t.values)).sort((a, b) => a - b)
  const range: [number, number] | undefined = sorted.length ? [percentile(sorted, 0.01) - 0.5, percentile(sorted, 0.9) + 1.0] : undefined
  return {
    x: rt.laps,
    xLabel: "Lap",
    markers: rt.box_laps.map((lap) => ({ x: lap, label: "box" })),
    panes: [
      { title: "Gap to best plan (+ = behind)", unit: "s", height: 200, decimals: 2, axisDecimals: 0, series: gap },
      { title: "Lap time (pit loss on the in-lap)", unit: "s", height: 170, decimals: 3, axisDecimals: 1, range, series: times },
    ],
  }
}

const finiteOrNull = (v: number | null | undefined): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null)

/** Whole session lap by lap: lap times (best / push / other), fuel used and average tyre wear; pit laps marked. */
export function sessionPaceTrace(laps: LapSummary[]): TraceData {
  if (!laps.length) return { x: [], panes: [] }
  const x = laps.map((l) => l.lap)
  const time = laps.map((l) => finiteOrNull(l.lap_time))
  const isBest = laps.map((l) => l.is_best)
  const isPush = laps.map((l) => l.lap_class === "push" && !l.is_best)
  const other = laps.map((_, i) => !isBest[i] && !isPush[i])
  const pushTimes = time.filter((t, i) => t != null && (isPush[i] || isBest[i])) as number[]
  const sorted = [...pushTimes].sort((a, b) => a - b)
  // Zoom on the push laps: out / in / SC laps would squash them into a flat line.
  const range: [number, number] | undefined = sorted.length >= 2 ? [sorted[0] - 0.5, sorted[sorted.length - 1] + Math.max(1, 0.25 * (sorted[sorted.length - 1] - sorted[0]))] : undefined
  const wear = laps.map((l) => finiteOrNull(l.tyre_wear_avg))
  const fuel = laps.map((l) => finiteOrNull(l.fuel_used))
  const panes: PaneSpec[] = [
    {
      title: "Lap time",
      unit: "s",
      height: 190,
      decimals: 3,
      axisDecimals: 1,
      range,
      series: [
        { label: "best", values: masked(time, isBest), color: DELTA, mode: "points", size: 9 },
        { label: "push", values: masked(time, isPush), color: FOCUS, mode: "points", size: 6 },
        { label: "other", values: masked(time, other), color: NEUTRAL, mode: "points", size: 6, hollow: true },
      ],
    },
  ]
  if (fuel.some((v) => v != null)) panes.push({ title: "Fuel used", unit: "kg/lap", height: 90, decimals: 2, series: [{ label: "fuel", values: fuel, color: REF, mode: "points", size: 5 }] })
  if (wear.some((v) => v != null)) panes.push({ title: "Tyre wear (avg)", unit: "%", height: 90, decimals: 1, series: [{ label: "wear", values: wear, color: THROTTLE, mode: "step" }] })
  const markers = laps.filter((l) => l.pit_stop).map((l) => ({ x: l.lap, label: "pit", color: NEUTRAL }))
  return { x, panes, xLabel: "Lap", xDecimals: 0, markers }
}
