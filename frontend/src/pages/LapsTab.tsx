import { useEffect, useMemo, useState } from "react"
import { useCompare, useLapChannels, useMap, useSession, useSessions } from "../api/hooks"
import type { LapSummary, SectorDelta, SessionDetail } from "../api/types"
import { TraceChart } from "../components/TraceChart"
import { TrackMap } from "../components/TrackMap"
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel, type Column } from "../components/ui"
import { selectGroup, useCursorStore } from "../lib/cursor"
import { fmt, fmtSigned, formatLapTime } from "../lib/format"
import { bestLapNumber, lapLabel, pbSession } from "../lib/sessions"
import { compareTrace, cornerBands, driverTrace, TRACE_CHANNELS } from "../lib/traces"

type RefMode = "none" | "lap" | "session"
const COLORS = ["speed", "throttle", "brake", "gear", "delta"] as const

interface Props {
  detail: SessionDetail
  focusLap: number | null
  setFocusLap: (lap: number) => void
}

function LapSelect({ laps, value, onChange, label }: { laps: LapSummary[]; value: number | null; onChange: (lap: number) => void; label: string }) {
  return (
    <label className="field">
      {label}
      <select value={value ?? ""} onChange={(e) => onChange(Number(e.target.value))} aria-label={label}>
        {laps.map((l) => (
          <option key={l.lap} value={l.lap}>
            {lapLabel(l, formatLapTime)}
          </option>
        ))}
      </select>
    </label>
  )
}

function sectorColumns(kind: "sector" | "mini_sector", name: string): Column<SectorDelta>[] {
  return [
    { key: "n", header: name, align: "right", render: (r) => r[kind] as number },
    { key: "from", header: "From (m)", align: "right", render: (r) => fmt(r.dist_start, 0) },
    { key: "to", header: "To (m)", align: "right", render: (r) => fmt(r.dist_end, 0) },
    { key: "d", header: "Δ (s)", align: "right", render: (r) => <span className={r.delta_s > 0 ? "bad" : "good"}>{fmtSigned(r.delta_s, 3)}</span> },
    { key: "c", header: "Cumulative (s)", align: "right", render: (r) => fmtSigned(r.delta_end, 3) },
  ]
}

export function LapsTab({ detail, focusLap, setFocusLap }: Props) {
  const { session, laps } = detail
  const sessions = useSessions()
  const resetCursor = useCursorStore((s) => s.reset)
  const cursor = useCursorStore(selectGroup("lap"))

  const best = bestLapNumber(laps)
  const [mode, setMode] = useState<RefMode>("none")
  const [refLap, setRefLap] = useState<number | null>(best)
  const [refSessionId, setRefSessionId] = useState<number | null>(null)
  const [color, setColor] = useState<(typeof COLORS)[number]>("speed")

  useEffect(() => {
    resetCursor("lap")
    setMode("none")
    setRefLap(bestLapNumber(laps))
    setRefSessionId(null)
    return () => resetCursor("lap")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id])

  const sameTrack = useMemo(() => (sessions.data ?? []).filter((s) => s.track === session.track && s.id !== session.id), [sessions.data, session.track, session.id])
  const pb = useMemo(() => pbSession(sessions.data?.filter((s) => s.track === session.track) ?? []), [sessions.data, session.track])
  const refDetail = useSession(refSessionId ?? 0, mode === "session" && refSessionId != null)
  const refLaps = mode === "session" ? (refDetail.data?.laps ?? []) : laps

  const chooseMode = (m: RefMode) => {
    setMode(m)
    if (m === "session") {
      const pick = pb && pb.id !== session.id ? pb.id : (sameTrack[0]?.id ?? null)
      setRefSessionId(pick)
      setRefLap(null) // filled once that session's laps arrive
    } else {
      setRefSessionId(null)
      setRefLap(best)
    }
  }
  useEffect(() => {
    if (mode === "session" && refDetail.data && (refLap == null || !refDetail.data.laps.some((l) => l.lap === refLap))) {
      setRefLap(bestLapNumber(refDetail.data.laps))
    }
  }, [mode, refDetail.data, refLap])

  const crossSession = mode === "session" && refSessionId != null
  const ref = useMemo(() => {
    if (mode === "none" || refLap == null || (mode === "session" && !refDetail.data)) return null
    if (crossSession) return { session: refSessionId, lap: refLap }
    return refLap === focusLap ? null : { session: null as number | null, lap: refLap }
  }, [mode, refLap, refDetail.data, crossSession, refSessionId, focusLap])

  const mapColor = color === "delta" && !ref ? "speed" : color
  const map = useMap(session.id, focusLap, ref?.lap ?? null, ref?.session ?? null, mapColor)
  const cmp = useCompare(session.id, focusLap, ref?.lap ?? null, ref?.session ?? null, !!ref)
  const single = useLapChannels(session.id, focusLap, TRACE_CHANNELS, !ref)

  const labels = useMemo(() => ({ cmp: `L${focusLap}`, ref: ref ? (ref.session ? `S${ref.session} L${ref.lap}` : `L${ref.lap}`) : "Ref" }), [focusLap, ref])
  // Keyed by content so a map refetch (e.g. new colour) does not rebuild the traces and lose the zoom.
  const spansKey = JSON.stringify(map.data?.spans ?? [])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const bands = useMemo(() => cornerBands(map.data?.spans), [spansKey])
  const traceData = useMemo(() => {
    if (ref) {
      if (!cmp.data) return null
      return { ...compareTrace(cmp.data, labels, 115), bands }
    }
    if (!single.data) return null
    return { ...driverTrace(single.data, labels, 115), bands }
  }, [ref, cmp.data, single.data, labels, bands])

  const focus = laps.find((l) => l.lap === focusLap)
  const cursorX = cursor.hoverX ?? cursor.pinnedX
  const cornerHere = cursorX != null ? map.data?.spans.find((s) => cursorX >= s.from && cursorX <= s.to)?.name : undefined

  const lapColumns: Column<LapSummary>[] = [
    { key: "lap", header: "Lap", align: "right", render: (l) => l.lap },
    { key: "class", header: "Class", render: (l) => l.lap_class },
    { key: "time", header: "Time", align: "right", render: (l) => formatLapTime(l.lap_time) },
    { key: "delta", header: "Δ best", align: "right", render: (l) => fmtSigned(l.delta_best, 3) },
    { key: "vmax", header: "Vmax", align: "right", render: (l) => fmt(l.vmax, 1) },
    { key: "full", header: "Full thr %", align: "right", render: (l) => fmt(l.throttle_full_pct, 1) },
    { key: "coast", header: "Coast %", align: "right", render: (l) => fmt(l.coast_pct, 1) },
    { key: "fuel", header: "Fuel used", align: "right", render: (l) => fmt(l.fuel_used, 2) },
    { key: "wear", header: "Wear avg %", align: "right", render: (l) => fmt(l.tyre_wear_avg, 1) },
    { key: "comp", header: "Compound", render: (l) => l.compound_label ?? "—" },
    { key: "lock", header: "Lockups", align: "right", render: (l) => fmt(l.lockup_samples, 0) },
  ]

  return (
    <div className="stack" data-testid="laps-tab">
      <Panel>
        <div className="row">
          <LapSelect laps={laps} value={focusLap} onChange={setFocusLap} label="Focus lap" />
          <label className="field">
            Reference
            <select value={mode} onChange={(e) => chooseMode(e.target.value as RefMode)} aria-label="Reference type">
              <option value="none">None</option>
              <option value="lap">Lap in this session</option>
              <option value="session" disabled={sameTrack.length === 0}>
                Another session
              </option>
            </select>
          </label>
          {mode === "session" && (
            <label className="field">
              Reference session
              <select value={refSessionId ?? ""} onChange={(e) => { setRefSessionId(Number(e.target.value)); setRefLap(null) }} aria-label="Reference session">
                {sameTrack.map((s) => (
                  <option key={s.id} value={s.id}>
                    #{s.id} · {s.session_type || "—"} · {s.lap_count} laps · best {formatLapTime(s.best_lap_time)}
                    {pb?.id === s.id ? " ★ PB" : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          {mode !== "none" && refLaps.length > 0 && <LapSelect laps={refLaps} value={refLap} onChange={setRefLap} label="Reference lap" />}
          <label className="field">
            Map colour
            <select value={color} onChange={(e) => setColor(e.target.value as (typeof COLORS)[number])} aria-label="Map colour">
              {COLORS.map((c) => (
                <option key={c} value={c} disabled={c === "delta" && !ref}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        </div>
        {mode === "lap" && !ref && <p className="note">Pick a different reference lap to see deltas and overlays.</p>}
      </Panel>

      <MetricRow>
        <Metric label="Focus lap" value={formatLapTime(focus?.lap_time)} sub={focus ? `${fmtSigned(focus.delta_best, 3)} s vs best` : ""} testId="metric-focus" />
        <Metric label="Best lap" value={`#${best ?? "—"} · ${formatLapTime(session.best_lap_time)}`} />
        <Metric label="Vmax" value={focus?.vmax != null ? `${focus.vmax.toFixed(1)} km/h` : "—"} />
        <Metric label="Cursor" value={cursorX != null ? `${cursorX.toFixed(0)} m` : "—"} sub={cursor.pinnedX != null && cursor.hoverX == null ? "pinned" : ""} testId="metric-cursor" />
        <Metric label="At corner" value={cornerHere ?? "—"} />
        {ref && cmp.data && (
          <Metric
            label="Lap Δ vs reference"
            value={`${fmtSigned(cmp.data.final_delta, 3)} s`}
            sub={cmp.data.final_delta != null && cmp.data.final_delta > 0 ? "slower" : "faster"}
            testId="metric-delta"
          />
        )}
      </MetricRow>

      <div className="grid-2">
        <Panel title={`${session.track ?? "Track"} — lap ${focusLap ?? "?"}${ref ? ` vs ${labels.ref}` : ""}`}>
          {map.isLoading && <Loading what="Loading map…" />}
          {map.isError && <ErrorBox error={map.error} />}
          {map.data && <TrackMap data={map.data} sync="lap" height={560} />}
        </Panel>
        <Panel title="Driver trace">
          {(ref ? cmp.isLoading : single.isLoading) && <Loading what="Loading channels…" />}
          {(ref ? cmp.isError : single.isError) && <ErrorBox error={ref ? cmp.error : single.error} />}
          {traceData && <TraceChart data={traceData} sync="lap" testId="driver-trace" />}
          <p className="note">Drag on a trace to zoom every pane · double-click to reset · click to pin the cursor.</p>
        </Panel>
      </div>

      {ref && cmp.data && (
        <div className="grid-2">
          <Panel title="Sector deltas">
            <DataTable columns={sectorColumns("sector", "Sector")} rows={cmp.data.sectors} rowKey={(r) => r.sector ?? 0} testId="sector-table" />
          </Panel>
          <Panel title="Mini-sector deltas">
            <DataTable columns={sectorColumns("mini_sector", "Mini")} rows={cmp.data.mini_sectors} rowKey={(r) => r.mini_sector ?? 0} maxHeight={300} testId="mini-sector-table" />
          </Panel>
        </div>
      )}

      <Panel title="Laps">
        <DataTable
          testId="laps-table"
          columns={lapColumns}
          rows={laps}
          rowKey={(l) => l.lap}
          rowClass={(l) => [l.is_best ? "best" : "", l.lap === focusLap ? "selected" : ""].join(" ")}
          onRowClick={(l) => setFocusLap(l.lap)}
          maxHeight={360}
        />
      </Panel>
    </div>
  )
}
