import { useEffect, useMemo, useState } from "react"
import { useCompare, useLapChannels, useLapExtras, useMap } from "../api/hooks"
import type { LapSummary, SectorDelta, SessionDetail } from "../api/types"
import { LapSelect, ReferenceFields, useReference } from "../components/ReferencePicker"
import { GGDiagram } from "../components/GGDiagram"
import { TraceChart } from "../components/TraceChart"
import { TrackMap } from "../components/TrackMap"
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel, type Column } from "../components/ui"
import { selectGroup, useCursorStore } from "../lib/cursor"
import { fmt, fmtSigned, formatLapTime } from "../lib/format"
import { bestLapNumber } from "../lib/sessions"
import { compareTrace, cornerBands, driverTrace, sessionPaceTrace, TRACE_CHANNELS } from "../lib/traces"
import { buildGG, GG_CHANNELS, GG_EXTRAS } from "../lib/gg"
import { loadExtras, saveExtras, usableExtras } from "../lib/extras"

const COLORS = ["speed", "throttle", "brake", "gear", "delta"] as const

interface Props {
  detail: SessionDetail
  focusLap: number | null
  setFocusLap: (lap: number) => void
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
  const resetCursor = useCursorStore((s) => s.reset)
  const cursor = useCursorStore(selectGroup("lap"))

  const best = bestLapNumber(laps)
  const choice = useReference(detail, "none")
  const { mode, selection } = choice
  const [color, setColor] = useState<(typeof COLORS)[number]>("speed")

  useEffect(() => {
    resetCursor("lap")
    return () => resetCursor("lap")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id])

  const ref = useMemo(() => {
    if (!selection) return null
    if (selection.session != null) return selection
    return selection.lap === focusLap ? null : selection
  }, [selection, focusLap])

  const mapColor = color === "delta" && !ref ? "speed" : color
  const map = useMap(session.id, focusLap, ref?.lap ?? null, ref?.session ?? null, mapColor)
  const extrasInfo = useLapExtras(session.id)
  const [picked, setPicked] = useState<string[]>(loadExtras)
  const extras = useMemo(() => usableExtras(picked, extrasInfo.data), [picked, extrasInfo.data])
  const togglePicked = (key: string) => {
    const next = picked.includes(key) ? picked.filter((k) => k !== key) : [...picked, key]
    setPicked(next)
    saveExtras(next)
  }
  const cmp = useCompare(session.id, focusLap, ref?.lap ?? null, ref?.session ?? null, !!ref, extras)
  const single = useLapChannels(session.id, focusLap, TRACE_CHANNELS, !ref, extras)

  const ggAvailable = !!extrasInfo.data && GG_EXTRAS.every((k) => extrasInfo.data!.find((e) => e.key === k)?.available)
  const ggChannels = useLapChannels(session.id, focusLap, GG_CHANNELS, ggAvailable, GG_EXTRAS)
  const gg = useMemo(() => buildGG(ggChannels.data), [ggChannels.data])
  const paceData = useMemo(() => sessionPaceTrace(laps), [laps])

  const labels = useMemo(() => ({ cmp: `L${focusLap}`, ref: ref ? (ref.session ? `S${ref.session} L${ref.lap}` : `L${ref.lap}`) : "Ref" }), [focusLap, ref])
  // Keyed by content so a map refetch (e.g. new colour) does not rebuild the traces and lose the zoom.
  const spansKey = JSON.stringify(map.data?.spans ?? [])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const bands = useMemo(() => cornerBands(map.data?.spans), [spansKey])
  const traceData = useMemo(() => {
    if (ref) {
      if (!cmp.data) return null
      return { ...compareTrace(cmp.data, labels, 115, extras), bands }
    }
    if (!single.data) return null
    return { ...driverTrace(single.data, labels, 115, extras), bands }
  }, [ref, cmp.data, single.data, labels, bands, extras])

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
      <Panel className="toolbar">
        <div className="row">
          <LapSelect laps={laps} value={focusLap} onChange={setFocusLap} label="Focus lap" />
          <ReferenceFields choice={choice} modes={["none", "lap", "session"]} />
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
        {extrasInfo.data && (
          <div className="row extras" role="group" aria-label="Extra channels" data-testid="extras-picker">
            <span className="toolbar-label">Extra panes</span>
            {extrasInfo.data.map((e) => (
              <label key={e.key} className={`field extra${e.available && picked.includes(e.key) ? " on" : ""}${e.available ? "" : " off"}`} title={e.available ? undefined : (e.reason ?? "Not available")}>
                <input type="checkbox" checked={e.available && picked.includes(e.key)} disabled={!e.available} onChange={() => togglePicked(e.key)} />
                {e.label}
                {!e.available && <span className="note"> ({e.reason})</span>}
              </label>
            ))}
          </div>
        )}
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
            value={<span className={cmp.data.final_delta != null && cmp.data.final_delta > 0 ? "bad" : "good"}>{fmtSigned(cmp.data.final_delta, 3)} s</span>}
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

      <div className="grid-2">
        <Panel title="Session pace" testId="session-pace">
          <TraceChart data={paceData} sync="pace" testId="session-pace-chart" />
          <p className="note">Every lap of the session: best, push and other laps (out / in / SC / slow); fuel used and average tyre wear per lap.</p>
        </Panel>
        <Panel title={`G-G · lap ${focusLap ?? "?"}`} testId="gg-panel">
          {!extrasInfo.data || (ggAvailable && ggChannels.isLoading) ? (
            <Loading what="Loading g-forces…" />
          ) : !ggAvailable ? (
            <p className="note">No g-force channels in this export.</p>
          ) : ggChannels.isError ? (
            <ErrorBox error={ggChannels.error} />
          ) : gg ? (
            <GGDiagram data={gg} />
          ) : (
            <p className="note">No g-force samples on this lap.</p>
          )}
        </Panel>
      </div>

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
