import { useEffect, useMemo, useState } from "react"
import {
  useAllocation,
  useClearAllocation,
  useCompoundModel,
  useInventory,
  useLapChannels,
  useSaveAllocation,
  useSaveTargets,
  useTyres,
} from "../api/hooks"
import type { SessionDetail, StintSummary, TyresPayload } from "../api/types"
import { CarGrid } from "../components/CarGrid"
import { StintTimeline } from "../components/StintTimeline"
import { TraceChart } from "../components/TraceChart"
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel, RecordTable, type Column } from "../components/ui"
import { fmt, fmtSigned } from "../lib/format"
import { stintSegments, stintTrace, tyreLapColumns, tyreLapTrace } from "../lib/traces"

interface Props {
  detail: SessionDetail
  focusLap: number | null
  setFocusLap: (lap: number) => void
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function stintColumns(limit: number): Column<StintSummary>[] {
  const mean = (s: StintSummary, ws: string[]) => {
    const vals = ws.map((w) => s.temp_mean[w]).filter((v): v is number => v != null)
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
  }
  return [
    { key: "n", header: "Stint", align: "right", render: (s) => s.stint.idx + 1 },
    { key: "comp", header: "Compound", render: (s) => <><span className="chip" style={{ background: s.color }} />{s.label}</> },
    { key: "laps", header: "Laps", render: (s) => `${s.stint.laps[0]}–${s.stint.laps[s.stint.laps.length - 1]} (${s.stint.laps.length})` },
    { key: "push", header: "Push laps", align: "right", render: (s) => s.stint.push_laps.length },
    { key: "deg", header: "Deg (s/lap)", align: "right", render: (s) => fmtSigned(s.deg.slope, 3) },
    { key: "r2", header: "R²", align: "right", render: (s) => fmt(s.deg.r2, 2) },
    { key: "cliff", header: "Cliff at age", align: "right", render: (s) => (s.deg.cliff_age != null ? String(s.deg.cliff_age) : "—") },
    { key: "lim", header: "Limiting", render: (s) => s.limiting_wheel ?? "—" },
    { key: "wr", header: "Wear (%/lap)", align: "right", render: (s) => fmt(s.limiting_wheel ? s.wear_rate[s.limiting_wheel] : null, 2) },
    { key: "wn", header: "Max wear (%)", align: "right", render: (s) => fmt(s.wear_now, 1) },
    { key: "ll", header: `Laps to ${limit.toFixed(0)}%`, align: "right", render: (s) => fmt(s.laps_to_limit, 1) },
    { key: "wu", header: "Warm-up (s)", align: "right", render: (s) => fmt(s.warmup_s, 2) },
    { key: "fuel", header: "Fuel (kg/lap)", align: "right", render: (s) => fmt(s.fuel_per_lap, 2) },
    {
      key: "t",
      header: "T front / rear (°C)",
      align: "right",
      render: (s) => {
        const f = mean(s, ["FL", "FR"])
        const r = mean(s, ["RL", "RR"])
        return f != null && r != null ? `${f.toFixed(0)} / ${r.toFixed(0)}` : "—"
      },
    },
  ]
}

function PressurePanel({ stint, kind }: { stint: StintSummary; kind: string }) {
  const save = useSaveTargets()
  const t = stint.targets
  const measured = (ws: string[]) => {
    const v = ws.map((w) => stint.hot_psi[w]).filter((x): x is number => x != null)
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
  }
  const [lo, setLo] = useState(t.temp_lo)
  const [hi, setHi] = useState(t.temp_hi)
  const r1 = (v: number) => Math.round(v * 10) / 10
  const [front, setFront] = useState(r1(t.hot_front_psi ?? measured(["FL", "FR"]) ?? 22))
  const [rear, setRear] = useState(r1(t.hot_rear_psi ?? measured(["RL", "RR"]) ?? 22))
  useEffect(() => {
    setLo(t.temp_lo)
    setHi(t.temp_hi)
    setFront(r1(t.hot_front_psi ?? measured(["FL", "FR"]) ?? 22))
    setRear(r1(t.hot_rear_psi ?? measured(["RL", "RR"]) ?? 22))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stint.stint.idx, stint.stint.compound, t.temp_lo, t.temp_hi, t.hot_front_psi, t.hot_rear_psi])
  const code = stint.stint.compound
  const num = (set: (v: number) => void) => (e: React.ChangeEvent<HTMLInputElement>) => set(Number(e.target.value))
  return (
    <Panel title={`Pressures & window — ${stint.label} (stint ${stint.stint.idx + 1}, push laps only)`} testId="pressure-panel">
      <div className="row">
        <label className="field">
          Window low (°C)
          <input type="number" step={1} value={lo} onChange={num(setLo)} />
        </label>
        <label className="field">
          Window high (°C)
          <input type="number" step={1} value={hi} onChange={num(setHi)} />
        </label>
        <label className="field">
          Hot target front (psi)
          <input type="number" step={0.1} value={front} onChange={num(setFront)} />
        </label>
        <label className="field">
          Hot target rear (psi)
          <input type="number" step={0.1} value={rear} onChange={num(setRear)} />
        </label>
        <button
          disabled={code == null || save.isPending}
          onClick={() => code != null && save.mutate({ code, kind, temp_lo: lo, temp_hi: hi, hot_front_psi: front, hot_rear_psi: rear })}
        >
          Save targets
        </button>
      </div>
      {save.isError && <ErrorBox error={save.error} />}
      {save.isSuccess && <p className="note">Saved targets for {stint.label}.</p>}
      <div style={{ marginTop: 8 }}>
        <RecordTable
          rows={stint.pressure}
          testId="pressure-table"
          formats={Object.fromEntries(Object.keys(stint.pressure[0] ?? {}).map((k) => [k, (v: number) => (/Change|Build/.test(k) ? fmtSigned(v, 1) : v.toFixed(1))]))}
        />
      </div>
      <p className="note">Cold set needed = cold set now + (hot target − hot measured). The game&apos;s build-up is small (~0–1 psi).</p>
    </Panel>
  )
}

function ModelPanel({ track, state, wearLimit }: { track: string; state: string; wearLimit: number }) {
  const model = useCompoundModel(track, state, wearLimit)
  const alloc = useAllocation(track)
  const saveAlloc = useSaveAllocation()
  const clearAlloc = useClearAllocation()
  const [pick, setPick] = useState<{ soft: number | null; medium: number | null; hard: number | null }>({ soft: null, medium: null, hard: null })
  useEffect(() => {
    if (alloc.data) setPick({ soft: alloc.data.soft, medium: alloc.data.medium, hard: alloc.data.hard })
  }, [alloc.data])

  const comps = Object.values(model.data?.compounds ?? {}).sort((a, b) => a.code - b.code)
  const columns: Column<(typeof comps)[number]>[] = [
    { key: "c", header: "Compound", render: (m) => <><span className="chip" style={{ background: m.color }} />{m.label}</> },
    { key: "o", header: "Offset vs ref (s)", align: "right", render: (m) => fmt(m.offset_s, 3) },
    { key: "d", header: "Deg (s/lap)", align: "right", render: (m) => fmt(m.deg_s_per_lap, 3) },
    { key: "w", header: "Wear (%/lap)", align: "right", render: (m) => fmt(m.wear_pct_per_lap, 2) },
    { key: "m", header: `Max laps @ ${wearLimit.toFixed(0)}%`, align: "right", render: (m) => m.max_laps ?? "—" },
    { key: "u", header: "Warm-up (s)", align: "right", render: (m) => fmt(m.warmup_s, 2) },
    { key: "s", header: "Stints / laps", align: "right", render: (m) => `${m.n_stints} / ${m.n_laps}` },
    { key: "src", header: "Source", render: (m) => m.source },
    { key: "n", header: "Note", render: (m) => <span className="dim">{m.note}</span> },
  ]
  const options = alloc.data?.options ?? []
  const picker = (role: "soft" | "medium" | "hard", label: string) => (
    <label className="field" key={role}>
      {label}
      <select value={pick[role] ?? ""} onChange={(e) => setPick({ ...pick, [role]: e.target.value === "" ? null : Number(e.target.value) })} aria-label={`${label} compound`}>
        <option value="">—</option>
        {options.map((o) => (
          <option key={o.code} value={o.code}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
  return (
    <Panel title={`Compound model — ${track} (all library sessions)`} testId="model-panel">
      {model.isLoading && <Loading what="Building the compound model…" />}
      {model.isError && <ErrorBox error={model.error} />}
      {model.data && comps.length === 0 && <p className="note">Not enough long runs on this track yet (need ≥4 push laps on one set).</p>}
      {comps.length > 0 && model.data && (
        <>
          <DataTable columns={columns} rows={comps} rowKey={(m) => m.code} testId="model-table" />
          <p className="note">
            Base pace {fmt(model.data.base_pace_s, 3)} s (new tyre, 5 kg) · pit loss{" "}
            {model.data.pit_loss ? `${model.data.pit_loss.toFixed(1)} s from ${model.data.pit_losses.length} stop(s)` : "not measured yet"} · sessions used:{" "}
            {model.data.sources.map((i) => `#${i}`).join(", ") || "—"}.
          </p>
        </>
      )}
      <div className="row" style={{ marginTop: 10 }}>
        {picker("soft", "S")}
        {picker("medium", "M")}
        {picker("hard", "H")}
        <button disabled={saveAlloc.isPending} onClick={() => saveAlloc.mutate({ track, ...pick })}>
          Save S/M/H
        </button>
        <button disabled={clearAlloc.isPending} onClick={() => clearAlloc.mutate(track)}>
          Use inferred
        </button>
        <span className="note">S/M/H for {track}: {alloc.data?.source ?? "…"}</span>
      </div>
    </Panel>
  )
}

function Body({ detail, tyres, focusLap, setFocusLap, limitInput, setLimitInput }: Props & { tyres: TyresPayload; limitInput: string; setLimitInput: (v: string) => void }) {
  const sessionId = detail.session.id
  const summaries = tyres.stints
  const focusStint = summaries.find((s) => focusLap != null && s.stint.laps.includes(focusLap)) ?? summaries[0]
  const inv = useInventory(sessionId)
  const cols = useMemo(() => tyreLapColumns(inv.data), [inv.data])
  const channels = useLapChannels(sessionId, focusLap, cols.all, !!inv.data && cols.all.length > 1)
  const traceData = useMemo(() => {
    if (!channels.data || !focusStint) return null
    return tyreLapTrace(channels.data, cols, { lo: focusStint.targets.temp_lo, hi: focusStint.targets.temp_hi })
  }, [channels.data, cols, focusStint])
  const stintData = useMemo(() => stintTrace(tyres), [tyres])
  const limit = tyres.wear_limit
  const columns = useMemo(() => stintColumns(limit), [limit])

  const row = tyres.wheel_table.find((r) => r.lap === focusLap)
  const lapsTotal = Math.max(1, ...tyres.wheel_table.map((r) => r.lap)) + 1
  const lim = focusStint?.limiting_wheel ?? null

  if (!focusStint) return <p className="note">No tyre stints found in this session.</p>
  return (
    <>
      <MetricRow>
        <Metric label="Compound" value={focusStint.label} testId="metric-compound" />
        <Metric label="Tyre age" value={`${focusLap != null ? (focusStint.stint.ages[String(focusLap)] ?? 0) : 0} laps`} sub="laps on this set before the focus lap" />
        <Metric label="Degradation" value={`${fmtSigned(focusStint.deg.slope, 3)} s/lap`} sub={`fuel-corrected, push laps · R² ${fmt(focusStint.deg.r2, 2)}`} />
        <Metric label={`Wear (${lim ?? "—"})`} value={`${fmt(lim ? focusStint.wear_rate[lim] : null, 2)} %/lap`} />
        <Metric label={`Laps to ${limit.toFixed(0)}%`} value={fmt(focusStint.laps_to_limit, 1)} />
        <div className="metric">
          <label className="field">
            Wear limit (%)
            <input type="number" min={30} max={95} step={1} value={limitInput} onChange={(e) => setLimitInput(e.target.value)} aria-label="Wear limit" />
          </label>
        </div>
      </MetricRow>

      <Panel title="Stints">
        <StintTimeline rows={[{ label: "This session", stints: stintSegments(summaries) }]} lapsTotal={lapsTotal} />
        <label className="field toolbar-row" style={{ marginTop: 10, maxWidth: 260 }}>
          Focus lap
          <select value={focusLap ?? ""} onChange={(e) => setFocusLap(Number(e.target.value))} aria-label="Focus lap">
            {detail.laps.map((l) => (
              <option key={l.lap} value={l.lap}>
                Lap {l.lap} — {l.lap_class}
              </option>
            ))}
          </select>
        </label>
      </Panel>

      <div className="grid-2-wide">
        <Panel title="Tyres over the lap">
          {channels.isLoading && <Loading what="Loading channels…" />}
          {channels.isError && <ErrorBox error={channels.error} />}
          {traceData && <TraceChart data={traceData} sync="lap" testId="tyre-lap-trace" />}
        </Panel>
        <Panel title={`Lap ${focusLap ?? "?"} · ${row?.lap_class ?? ""} lap`}>
          {row && <CarGrid row={row} targets={focusStint.targets} wearRate={focusStint.wear_rate} />}
          {tyres.temp_channel && <p className="note">Temperature channel: {tyres.temp_channel}.</p>}
        </Panel>
      </div>

      <Panel title="Stints table">
        <DataTable testId="stints-table" columns={columns} rows={summaries} rowKey={(s) => s.stint.idx} />
      </Panel>

      <Panel title="Stint trends">
        <TraceChart data={stintData} sync="stint" testId="stint-trace" />
        <p className="note">
          Lap times corrected to 5 kg with {tyres.race_stats.fuel_s_per_kg.toFixed(3)} s/kg (fuel + track evolution,{" "}
          {tyres.race_stats.fuel_pairs ? `measured from ${tyres.race_stats.fuel_pairs} same-compound stint pairs in your races` : "default"}). Hollow points = start / in / pit / out / SC / slow
          laps, left out of the trends. Drag to zoom, double-click to reset.
        </p>
      </Panel>

      <PressurePanel stint={focusStint} kind={tyres.temp_kind} />
      <ModelPanel track={tyres.track} state={tyres.state} wearLimit={limit} />
    </>
  )
}

export function TyresTab({ detail, focusLap, setFocusLap }: Props) {
  const [limitInput, setLimitInput] = useState("")
  const debounced = useDebounced(limitInput, 500)
  const wearLimit = debounced !== "" && Number.isFinite(Number(debounced)) && Number(debounced) >= 1 && Number(debounced) <= 100 ? Number(debounced) : null
  const tyres = useTyres(detail.session.id, wearLimit)
  useEffect(() => {
    if (limitInput === "" && tyres.data) setLimitInput(String(tyres.data.wear_limit))
  }, [tyres.data, limitInput])

  return (
    <div className="stack" data-testid="tyres-tab">
      {tyres.isLoading && <Loading what="Analysing tyres…" />}
      {tyres.isError && <ErrorBox error={tyres.error} />}
      {tyres.data && <Body detail={detail} tyres={tyres.data} focusLap={focusLap} setFocusLap={setFocusLap} limitInput={limitInput} setLimitInput={setLimitInput} />}
    </div>
  )
}
