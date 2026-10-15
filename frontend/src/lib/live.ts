/** Live view: message types, delta trace buffer and the WebSocket hook. */
import { useEffect, useRef, useState } from "react"
import type { EngineerView } from "../api/types"

export type WheelStatus = "cold" | "ok" | "hot"
export interface LiveWheel {
  surface: number
  inner: number
  press_psi: number
  wear: number | null
  damage: number | null
  blister: number | null
  brake_temp: number
  brake_damage?: number | null
  status: WheelStatus
  inner_status: WheelStatus
  wear_status: "ok" | "high" | "limit"
}
export interface LiveRival {
  pos: number
  name: string
  you: boolean
  gap_s: number | null
  compound: number | null
  label: string | null
  age: number | null
  stops: number
  last: number | null
  in_pit: boolean
  threat: boolean
  wing_damage?: number | null
}
export interface LiveDamage {
  parts: { part: string; group: "aero" | "power"; pct: number; hit_lap: number | null }[]
  wear: { part: string; pct: number }[]
  faults: string[]
  front_wing_pct: number
  loss: { loss_s: number; laps_before: number; laps_after: number; fuel_fix_s: number } | null
  advice: { call: "BOX" | "STAY" | "AT_STOP" | "MEASURE" | null; text: string | null }
  note: string | null
  any: boolean
}
export interface LiveStrategy {
  available: boolean
  reason?: string
  call?: "BOX" | "STAY"
  call_green?: "BOX" | "STAY"
  call_sc?: "BOX" | "STAY"
  box_window?: [number, number] | null
  no_more_stops?: boolean
  best_in_laps?: number
  fit_label?: string | null
  box_now_s?: number | null
  stay_out_s?: number | null
  box_under_sc_s?: number | null
  laps_left?: number
  updated_lap?: number
  pit_loss_s?: number
  sc?: number
}
export interface LiveSnapshot {
  type: "snapshot"
  t: number
  session: {
    track: string
    type: string
    lap: number
    total_laps: number
    position: number
    weather: string
    track_temp: number
    air_temp: number
    sc: number
    sc_name: string
    forecast: { in_min: number; weather: string; rain_pct: number }[]
    game_pit_window: [number, number] | null
    pit_status: number
    penalties_s: number
    time_left_s?: number
  }
  timing: {
    lap_time: number
    last: number | null
    best: number | null
    best_lap: number | null
    sectors: (number | null)[]
    sector: number
    delta_best: number | null
    delta_last: number | null
    predicted: number | null
    lap_distance: number
    invalid: boolean
  }
  tyres: {
    compound: number
    label: string
    age: number
    wear_limit: number
    wheels: Record<"FL" | "FR" | "RL" | "RR", LiveWheel>
    targets: { surface: [number, number]; inner: [number, number] }
  }
  fuel: { kg: number; capacity: number; per_lap: number | null; laps_left: number | null; margin_laps: number | null; game_laps_left: number; mix?: number }
  ers: { store_mj: number; mode: number; deployed_mj: number; harvested_mj: number; harvest_limit_mj: number; overtake: boolean | null; overtake_available: boolean | null; active_aero: number | null }
  damage: LiveDamage | null
  rivals: LiveRival[]
  strategy: LiveStrategy | null
  /** Race engineer view; null/absent while no program runs. */
  engineer?: EngineerView | null
}
export interface LiveStatus {
  type: "status"
  connected: boolean
  enabled?: boolean
  packets_per_s?: number
  frame_gap_pct?: number
  recording?: boolean
  udp_error?: string | null
}
export interface LiveEvent {
  type: "event"
  kind: string
  text: string
  t: number
}

export const ERS_MODES = ["None", "Medium", "Hotlap", "Overtake"]
const COMPOUND_COLORS: Record<number, string> = { 22: "#B5179E", 16: "#D7263D", 17: "#E8A317", 18: "#C9CED6", 19: "#8A9099", 20: "#5C6670", 21: "#3A4148", 7: "#2E9E44", 8: "#1F6FD1" }
export const compoundColor = (code: number | null | undefined) => (code != null ? COMPOUND_COLORS[code] ?? "#8A9099" : "#8A9099")

/** Delta-vs-distance points of the current lap; resets when the lap distance wraps. */
export function pushDelta(points: [number, number][], dist: number, delta: number | null, maxPoints = 1500): [number, number][] {
  if (delta == null || !Number.isFinite(delta)) return points
  const last = points[points.length - 1]
  const next = last && dist < last[0] - 200 ? [] : points.slice()
  if (next.length && dist <= next[next.length - 1][0]) return next
  next.push([dist, delta])
  return next.length > maxPoints ? next.slice(next.length - maxPoints) : next
}

/** Signed gap to a rival: negative = ahead. */
export function gapLabel(gap: number | null): string {
  if (gap == null || !Number.isFinite(gap)) return "—"
  if (Math.abs(gap) < 0.05) return "0.0"
  return `${gap > 0 ? "+" : "−"}${Math.abs(gap).toFixed(1)}`
}

export interface LiveData {
  snapshot: LiveSnapshot | null
  status: LiveStatus | null
  events: LiveEvent[]
  deltaTrace: [number, number][]
  lastTrace: [number, number][]
  socket: "connecting" | "open" | "closed"
  lastAt: number
}

export function useLive(): LiveData {
  const [data, setData] = useState<LiveData>({ snapshot: null, status: null, events: [], deltaTrace: [], lastTrace: [], socket: "connecting", lastAt: 0 })
  const trace = useRef<[number, number][]>([])
  const traceLast = useRef<[number, number][]>([])
  useEffect(() => {
    let ws: WebSocket | null = null
    let timer: number | undefined
    let stopped = false
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws"
      ws = new WebSocket(`${proto}://${location.host}/ws/live`)
      ws.onopen = () => setData((d) => ({ ...d, socket: "open" }))
      ws.onclose = () => {
        setData((d) => ({ ...d, socket: "closed" }))
        if (!stopped) timer = window.setTimeout(connect, 1500)
      }
      ws.onmessage = (ev) => {
        let m: { type?: string }
        try {
          m = JSON.parse(ev.data)
        } catch {
          return
        }
        if (m.type === "snapshot") {
          const s = m as unknown as LiveSnapshot
          trace.current = pushDelta(trace.current, s.timing.lap_distance, s.timing.delta_best)
          traceLast.current = pushDelta(traceLast.current, s.timing.lap_distance, s.timing.delta_last)
          setData((d) => ({ ...d, snapshot: s, deltaTrace: trace.current, lastTrace: traceLast.current, lastAt: Date.now() }))
        } else if (m.type === "status") {
          setData((d) => ({ ...d, status: m as unknown as LiveStatus }))
        } else if (m.type === "event") {
          setData((d) => ({ ...d, events: [m as unknown as LiveEvent, ...d.events].slice(0, 4) }))
        }
      }
    }
    connect()
    return () => {
      stopped = true
      window.clearTimeout(timer)
      if (ws) {
        ws.onopen = ws.onclose = ws.onmessage = null
        ws.close()
      }
    }
  }, [])
  return data
}
