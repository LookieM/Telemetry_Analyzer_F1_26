import { useEffect, useMemo, useState } from "react"
import { ApiError } from "../api/client"
import { useBalance, useCompare, useCorners, useMap, useRebuildCorners } from "../api/hooks"
import type { SessionDetail } from "../api/types"
import { BalanceStrip } from "../components/BalanceStrip"
import { LapSelect, ReferenceFields, useReference } from "../components/ReferencePicker"
import { TraceChart } from "../components/TraceChart"
import { TrackMap, type MapMark } from "../components/TrackMap"
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel, type Column } from "../components/ui"
import { balanceUnavailable, buildBalanceColumns } from "../lib/balance"
import { biggestLoss, buildCornerRows, cornerAt, cornerMarkers, lossKind, sortRows, zoomRange, type CornerRow, type SortDir, type SortKey } from "../lib/corners"
import { selectGroup, useCursorStore } from "../lib/cursor"
import { fmt, fmtSigned } from "../lib/format"
import { fastestOtherLap } from "../lib/sessions"
import { compareTrace, cornerBands } from "../lib/traces"
import "./CornersTab.css"

const SYNC = "corners"
const SPEED_STEP_KMH = 3

interface Props {
  detail: SessionDetail
  focusLap: number | null
  setFocusLap: (lap: number) => void
}

function SortHeader({ label, k, sort, onSort }: { label: string; k: SortKey; sort: { key: SortKey; dir: SortDir }; onSort: (k: SortKey) => void }) {
  const active = sort.key === k
  return (
    <button className={`ct-sort${active ? " active" : ""}`} onClick={() => onSort(k)} title="Sort by this column">
      {label}
      {active ? (sort.dir === "asc" ? " ▲" : " ▼") : ""}
    </button>
  )
}

/** A value with its difference to the reference; speed differences are coloured (higher is better). */
function Value({ v, d, decimals = 0, speed = false, unit = "" }: { v: number | null; d: number | null; decimals?: number; speed?: boolean; unit?: string }) {
  const tone = speed && d != null && Math.abs(d) >= SPEED_STEP_KMH ? (d > 0 ? "good" : "bad") : ""
  return (
    <>
      {fmt(v, decimals)}
      {unit}
      {d != null && <span className={`ct-delta ${tone}`}>{fmtSigned(d, decimals)}</span>}
    </>
  )
}

export function CornersTab({ detail, focusLap, setFocusLap }: Props) {
  const { session, laps } = detail
  const choice = useReference(detail, "lap")
  const { selection } = choice
  const resetCursor = useCursorStore((s) => s.reset)
  const cursor = useCursorStore(selectGroup(SYNC))
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "order", dir: "asc" })
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [balanceView, setBalanceView] = useState<"lap" | "session">("lap")

  useEffect(() => {
    resetCursor(SYNC)
    setSelectedId(null)
    return () => resetCursor(SYNC)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id])

  // The same lap as focus and reference shows only zeros: start from the fastest other clean lap instead.
  useEffect(() => {
    if (choice.mode === "lap" && choice.refLap != null && choice.refLap === focusLap) {
      const other = fastestOtherLap(laps, focusLap)
      if (other != null) choice.setRefLap(other)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id, focusLap, choice.mode, choice.refLap])

  const refLap = selection?.lap ?? null
  const refSession = selection?.session ?? null
  const corners = useCorners(session.id, focusLap, refLap, refSession, !!selection)
  const cmp = useCompare(session.id, focusLap, refLap, refSession, !!selection)
  const map = useMap(session.id, focusLap, refLap, refSession, "speed")
  const rebuild = useRebuildCorners()
  const sessionBalance = useBalance(session.id, balanceView === "session")

  const rows = useMemo(() => (corners.data ? buildCornerRows(corners.data) : []), [corners.data])
  const shown = useMemo(() => sortRows(rows, sort.key, sort.dir), [rows, sort])
  const selected = rows.find((r) => r.id === selectedId) ?? null
  const worst = useMemo(() => biggestLoss(rows), [rows])
  const trackLength = map.data?.track_length ?? null
  const zoom = selected ? zoomRange(selected, trackLength) : null

  const labels = useMemo(() => ({ cmp: `L${focusLap}`, ref: selection ? (selection.session ? `S${selection.session} L${selection.lap}` : `L${selection.lap}`) : "Ref" }), [focusLap, selection])
  const bands = useMemo(() => cornerBands(rows.map((r) => ({ from: r.startM, to: r.endM, name: r.name }))), [rows])
  const traceData = useMemo(() => {
    if (!cmp.data) return null
    return { ...compareTrace(cmp.data, labels, 115), bands, markers: selected ? cornerMarkers(selected) : [] }
  }, [cmp.data, labels, bands, selected])
  const marks = useMemo<MapMark[]>(() => (selected ? cornerMarkers(selected).map((m) => ({ d: m.x, label: m.label ?? "", color: m.color ?? "#888" })) : []), [selected])

  const onSort = (key: SortKey) => setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "order" ? "asc" : key === "timeDelta" ? "desc" : "asc" }))
  const select = (row: CornerRow) => setSelectedId((cur) => (cur === row.id ? null : row.id))

  const head = (label: string, k: SortKey) => <SortHeader label={label} k={k} sort={sort} onSort={onSort} />
  const columns: Column<CornerRow>[] = [
    { key: "order", header: head("#", "order"), align: "right", render: (r) => r.order },
    {
      key: "name",
      header: "Corner",
      render: (r) => (
        <span className="ct-name" title={`${fmt(r.startM, 0)}–${fmt(r.endM, 0)} m${r.complex ? " · complex of several minima" : ""}`}>
          {r.name}
          <span className="tag ct-class">{r.speedClass}</span>
        </span>
      ),
    },
    { key: "time", header: head("Time (s)", "time"), align: "right", render: (r) => fmt(r.time, 3) },
    {
      key: "timeDelta",
      header: head("Δ time (s)", "timeDelta"),
      align: "right",
      title: "Time in the corner minus the reference; corner deltas plus the straights add up to the lap delta",
      render: (r) => <span className={`ct-${lossKind(r.timeDelta)}`}>{fmtSigned(r.timeDelta, 3)}</span>,
    },
    { key: "entry", header: head("Entry km/h", "entry"), align: "right", render: (r) => <Value v={r.entry} d={r.entryDelta} speed /> },
    { key: "vmin", header: head("Min km/h", "vmin"), align: "right", render: (r) => <Value v={r.vmin} d={r.vminDelta} speed /> },
    { key: "exit", header: head("Exit km/h", "exit"), align: "right", render: (r) => <Value v={r.exit} d={r.exitDelta} speed /> },
    { key: "brake", header: head("Brake at (m)", "brake"), align: "right", title: "Negative difference = braking earlier than the reference", render: (r) => <Value v={r.brake} d={r.brakeDelta} /> },
    { key: "trail", header: head("Trail brake (m)", "trail"), align: "right", render: (r) => <Value v={r.trail} d={r.trailDelta} /> },
    { key: "throttle", header: head("Full throttle at (m)", "throttle"), align: "right", title: "Positive difference = later on the throttle", render: (r) => <Value v={r.throttle} d={r.throttleDelta} /> },
  ]

  const callouts = useMemo(
    () => [...rows].filter((r) => r.callouts.length).sort((a, b) => Math.abs(b.timeDelta ?? 0) - Math.abs(a.timeDelta ?? 0)),
    [rows],
  )
  const cursorX = cursor.hoverX ?? cursor.pinnedX
  const cornerHere = cornerAt(rows, cursorX)
  const data = corners.data
  const balanceBase = data?.balance_baseline
  const shownBalance = balanceView === "session" ? sessionBalance.data : data
  const balanceColumns = useMemo(() => {
    if (!data || !balanceBase) return []
    if (balanceView === "session") return sessionBalance.data ? buildBalanceColumns(sessionBalance.data.corners.map((c) => ({ id: c.id, name: c.name, balance: c })), balanceBase) : []
    return buildBalanceColumns(data.corners, balanceBase)
  }, [data, balanceBase, balanceView, sessionBalance.data])
  const noData = corners.error instanceof ApiError && (corners.error.status === 404 || corners.error.status === 422)

  return (
    <div className="stack" data-testid="corners-tab">
      <Panel
        title="Where and why do I lose time?"
        actions={
          data && focusLap != null ? (
            <button
              disabled={rebuild.isPending}
              title="Detect this track's corners again from the focus lap"
              onClick={() => {
                if (window.confirm(`Rebuild the corners of ${session.track} from lap ${focusLap}? Every session of the track will use them.`))
                  rebuild.mutate({ track: data.track, session: session.id, lap: focusLap })
              }}
            >
              Rebuild corners from lap {focusLap}
            </button>
          ) : undefined
        }
      >
        <div className="row">
          <LapSelect laps={laps} value={focusLap} onChange={setFocusLap} label="Focus lap" />
          <ReferenceFields choice={choice} modes={["lap", "session"]} />
        </div>
        {data && (
          <p className="note">
            Corners detected from {data.corners_source.session === session.id ? "this session's" : `session #${data.corners_source.session}'s`} lap {data.corners_source.lap}. Time in a corner is measured from the aligned delta, positive = slower than the reference.
          </p>
        )}
        {data && data.lap === data.reference.lap && data.reference.session === session.id && (
          <p className="note" data-testid="corners-same-lap">Focus and reference are the same lap, so every difference is zero. Pick another focus or reference lap.</p>
        )}
        {rebuild.isError && <ErrorBox error={rebuild.error} />}
      </Panel>

      {!selection && <p className="note">Pick a reference lap to compare against.</p>}
      {corners.isLoading && <Loading what="Detecting corners and comparing laps…" />}
      {corners.isError && (noData ? <p className="note" data-testid="corners-nodata">Not enough data for corners: {(corners.error as ApiError).message}</p> : <ErrorBox error={corners.error} />)}

      {data && (
        <>
          <MetricRow>
            <Metric label="Lap Δ vs reference" value={`${fmtSigned(data.lap_delta, 3)} s`} sub={data.lap_delta > 0 ? "slower" : "faster"} testId="metric-lap-delta" />
            <Metric label="In corners" value={`${fmtSigned(data.sum_corner_delta, 3)} s`} sub={`${rows.length} corners`} testId="metric-corner-sum" />
            <Metric label="On straights" value={`${fmtSigned(data.straights_delta, 3)} s`} sub="between the corners" testId="metric-straights" />
            <Metric label="Biggest loss" value={worst ? worst.name : "—"} sub={worst ? `${fmtSigned(worst.timeDelta, 3)} s` : "nothing above the noise"} testId="metric-worst" />
            <Metric label="At cursor" value={cursorX != null ? `${cursorX.toFixed(0)} m` : "—"} sub={cornerHere ?? ""} />
          </MetricRow>

          <Panel title={`${data.track} corners — lap ${data.lap} vs ${data.reference.session !== session.id ? `#${data.reference.session} ` : ""}lap ${data.reference.lap}`}>
            <DataTable
              testId="corner-table"
              columns={columns}
              rows={shown}
              rowKey={(r) => r.id}
              rowClass={(r) => (r.id === selectedId ? "selected ct-selected" : undefined)}
              onRowClick={select}
              maxHeight={440}
            />
            <p className="note">Click a corner to zoom the map and traces to it · click again to show the whole lap · click a column title to sort.</p>
          </Panel>

          <div className="grid-2">
            <Panel
              title={selected ? `${selected.name} (${selected.speedClass}) · ${fmt(selected.startM, 0)}–${fmt(selected.endM, 0)} m` : `${data.track} — lap ${data.lap}`}
              actions={selected ? <button onClick={() => setSelectedId(null)}>Whole lap</button> : undefined}
            >
              {map.isLoading && <Loading what="Loading map…" />}
              {map.isError && <ErrorBox error={map.error} />}
              {map.data && <TrackMap data={map.data} sync={SYNC} height={520} zoom={zoom} marks={marks} />}
            </Panel>
            <Panel title="Driver trace">
              {cmp.isLoading && <Loading what="Loading channels…" />}
              {cmp.isError && <ErrorBox error={cmp.error} />}
              {traceData && <TraceChart data={traceData} sync={SYNC} testId="corner-trace" zoom={zoom} />}
              <p className="note">Drag on a trace to zoom · double-click to reset · click to pin the cursor. Dashed lines mark the brake and full-throttle points of the selected corner.</p>
            </Panel>
          </div>

          <Panel
            title="Balance, traction and lock-ups"
            testId="balance-panel"
            actions={
              <div className="bal-modes">
                <button className={balanceView === "lap" ? "active" : ""} onClick={() => setBalanceView("lap")} title="Balance of the focus lap">
                  Lap {focusLap}
                </button>
                <button className={balanceView === "session" ? "active" : ""} onClick={() => setBalanceView("session")} title="Median over the session's clean laps, so one mistake does not decide">
                  Session median
                </button>
              </div>
            }
          >
            {balanceView === "session" && sessionBalance.isLoading && <Loading what="Measuring balance over the clean laps…" />}
            {balanceView === "session" && sessionBalance.isError && <ErrorBox error={sessionBalance.error} />}
            {shownBalance && balanceUnavailable(shownBalance) ? (
              <p className="note" data-testid="balance-nodata">Not enough data for balance: {balanceUnavailable(shownBalance)}</p>
            ) : (
              shownBalance && (
                <>
                  <p className="bal-summary" data-testid="balance-summary">
                    {shownBalance.balance_summary ?? "—"}
                  </p>
                  <p className="note">
                    {balanceView === "session" && sessionBalance.data ? `Median over ${sessionBalance.data.laps} clean laps (${sessionBalance.data.lap_numbers.join(", ")}).` : `Focus lap ${data.lap}.`}
                  </p>
                  <BalanceStrip columns={balanceColumns} selectedId={selectedId} onSelect={(id) => setSelectedId((cur) => (cur === id ? null : id))} lockups={shownBalance.lockups} />
                </>
              )
            )}
          </Panel>

          <Panel title="What changed">
            {callouts.length === 0 ? (
              <p className="note" data-testid="corner-callouts-empty">No corner differs from the reference by more than the noise ({"±"}0.03 s).</p>
            ) : (
              <ul className="ct-callouts" data-testid="corner-callouts">
                {callouts.map((r) => (
                  <li key={r.id} className={lossKind(r.timeDelta) === "flat" ? "" : lossKind(r.timeDelta)} onClick={() => select(r)}>
                    {r.callouts[0]}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}
