import { useEffect, useState } from "react"
import { Link, Navigate, useNavigate, useParams } from "react-router-dom"
import { useNameSetup, useRunDuel, useSetBaseline, useTrackBaseline, useTrackCatalog, useTrackSetups } from "../api/hooks"
import type { BaselinePayload, BaselineRequest, DuelContestant, DuelResult, SetupCandidate, SetupRunRow } from "../api/types"
import { DataTable, ErrorBox, Loading, Panel, type Column } from "../components/ui"
import { copyText, copyToClipboard, groupValues, sourceLabel, valueText } from "../lib/baseline"
import { balanceCell, balanceDistance, canRank, gapVsLeader, pickHint, setupLabel, togglePick, verdict, wearText } from "../lib/duel"
import { fmt, formatDate, formatLapTime } from "../lib/format"
import "./Setups.css"

/** /setups: jump to the first track that has sessions. */
export function SetupsIndex() {
  const catalog = useTrackCatalog()
  if (catalog.isLoading) return <Loading />
  const first = catalog.data?.tracks.find((t) => t.sessions > 0)
  if (!first) return <p className="note">No sessions in the library yet, so there are no setups to compare.</p>
  return <Navigate to={`/track/${encodeURIComponent(first.track)}/setups`} replace />
}

function NameEditor({ setup, track }: { setup: SetupCandidate; track: string }) {
  const rename = useNameSetup(track)
  const [text, setText] = useState(setup.name ?? "")
  useEffect(() => setText(setup.name ?? ""), [setup.name])
  const save = () => {
    if (text.trim() !== (setup.name ?? "")) rename.mutate({ fingerprint: setup.fingerprint, name: text })
  }
  return (
    <input
      className="setup-name"
      value={text}
      placeholder={setupLabel({ fingerprint: setup.fingerprint, name: null })}
      maxLength={60}
      aria-label="Setup name"
      onChange={(e) => setText(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
    />
  )
}

const RUN_COLUMNS: Column<SetupRunRow>[] = [
  { key: "session", header: "Session", render: (r) => <Link to={`/session/${r.session_id}/laps`}>#{r.session_id}</Link> },
  { key: "type", header: "Type", render: (r) => (r.session_type ? <span className="tag">{r.session_type}</span> : <span className="dim">—</span>) },
  { key: "laps", header: "Laps", render: (r) => `${r.first_lap}–${r.last_lap}` },
  { key: "clean", header: "Clean", align: "right", title: "Clean laps counted in a duel (no in / out / pit / invalid laps, no big mistakes)", render: (r) => `${r.n_clean}/${r.n_laps}` },
  { key: "compound", header: "Compound", render: (r) => r.compound_label },
  { key: "state", header: "Track", render: (r) => r.state },
  { key: "fuel", header: "Fuel", align: "right", render: (r) => (r.fuel_kg != null ? `${fmt(r.fuel_kg, 0)} kg` : "—") },
  { key: "pace", header: "Pace", align: "right", title: "Median fuel-corrected clean lap", render: (r) => formatLapTime(r.pace_s) },
  { key: "best", header: "Best", align: "right", render: (r) => formatLapTime(r.best_s) },
  { key: "wear", header: "Wear", align: "right", render: (r) => wearText(r.wear_pct_per_lap) },
]

type MakeBaseline = (body: BaselineRequest) => void

function SetupCard({ setup, track, picked, onToggle, onBaseline }: { setup: SetupCandidate; track: string; picked: boolean; onToggle: () => void; onBaseline: MakeBaseline }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`setup-card${picked ? " picked" : ""}`} data-testid="setup-card">
      <div className="setup-head">
        <label className="setup-pick" title="Pick for a duel">
          <input type="checkbox" checked={picked} onChange={onToggle} aria-label={`Pick ${setupLabel(setup)}`} />
        </label>
        <NameEditor setup={setup} track={track} />
        <span className="dim mono">{setup.fingerprint.slice(0, 8)}</span>
        <span className="dim">
          {setup.n_runs} run{setup.n_runs === 1 ? "" : "s"} · {setup.n_clean} clean laps · last driven {formatDate(setup.last_driven)}
        </span>
        <span className="spacer" />
        {setup.runs.length > 0 && (
          <button className="ghost" title="Use this setup (from its latest session) as the track baseline" onClick={() => onBaseline({ session_id: setup.runs[0].session_id, name: setupLabel(setup) })} data-testid="make-baseline-setup">
            Make baseline
          </button>
        )}
        <button className="ghost" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide runs" : "Runs"}
        </button>
      </div>
      {open && <DataTable columns={RUN_COLUMNS} rows={setup.runs} rowKey={(r) => `${r.session_id}-${r.run}`} />}
    </div>
  )
}

function BaselineCard({ track, baseline, loading, error, saveError, onRestore }: { track: string; baseline: BaselinePayload | undefined; loading: boolean; error: unknown; saveError: unknown; onRestore: (id: number) => void }) {
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null)
  const active = baseline?.active ?? null
  const older = (baseline?.history ?? []).filter((h) => !h.active)
  const copy = async () => {
    if (!active) return
    setCopied((await copyToClipboard(copyText(`${track} baseline: ${active.name}`, active.display))) ? "ok" : "fail")
    window.setTimeout(() => setCopied(null), 2500)
  }
  return (
    <Panel
      title="Track baseline"
      testId="baseline-card"
      actions={
        active && (
          <button className="ghost" onClick={() => void copy()} data-testid="copy-baseline">
            {copied === "ok" ? "Copied" : copied === "fail" ? "Copy failed" : "Copy as text"}
          </button>
        )
      }
    >
      {loading && <Loading what="Reading the baseline…" />}
      {error != null && <ErrorBox error={error} />}
      {saveError != null && <ErrorBox error={saveError} />}
      {baseline && !active && <p className="note">No baseline for this track yet. Make one from a duel winner, a setup below, or when the engineer finishes a program.</p>}
      {active && (
        <>
          <p className="baseline-meta" data-testid="baseline-meta">
            <b>{active.name}</b> <span className="tag">{sourceLabel(active.source)}</span> <span className="dim">set {formatDate(active.created_at)}</span>
          </p>
          <div className="baseline-groups" data-testid="baseline-values">
            {groupValues(active.display).map((g) => (
              <div key={g.group} className="baseline-group">
                <h4>{g.group}</h4>
                <dl>
                  {g.items.map((it) => (
                    <div key={it.key} className="baseline-row">
                      <dt>{it.label}</dt>
                      <dd className="mono">{valueText(it)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        </>
      )}
      {older.length > 0 && (
        <details className="baseline-history" data-testid="baseline-history">
          <summary>History · {older.length} older</summary>
          <ul>
            {older.map((h) => (
              <li key={h.id}>
                <b>{h.name}</b> <span className="tag">{sourceLabel(h.source)}</span> <span className="dim">{formatDate(h.created_at)}</span>
                <button className="ghost" onClick={() => onRestore(h.id)} data-testid={`restore-baseline-${h.id}`}>
                  Restore
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  )
}

function ResultTable({ result, onBaseline }: { result: DuelResult; onBaseline: MakeBaseline }) {
  const r = result.ranking
  if (!r) return null
  const columns: Column<DuelContestant>[] = [
    { key: "rank", header: "#", align: "right", render: (c) => c.rank },
    { key: "name", header: "Setup", render: (c) => <b>{c.name}</b> },
    { key: "laps", header: "Laps", align: "right", render: (c) => c.n_laps },
    { key: "race", header: "Race pace", align: "right", title: "Mean of the corrected clean laps", render: (c) => formatLapTime(c.race_pace_s) },
    { key: "quali", header: "Quali pace", align: "right", title: "Best corrected lap", render: (c) => formatLapTime(c.quali_pace_s) },
    { key: "wear", header: "Wear", align: "right", render: (c) => wearText(c.wear_pct_per_lap) },
    { key: "cost", header: "Race cost", align: "right", title: "What its tyre wear costs per lap over a 50 % race, vs the gentlest setup", render: (c) => `${fmt(c.race_cost_s, 3)} s` },
    { key: "score", header: "Score", align: "right", title: `${Math.round(r.weights.race * 100)} % race pace + cost, ${Math.round(r.weights.quali * 100)} % one-lap pace`, render: (c) => formatLapTime(c.score_s) },
    {
      key: "gap",
      header: "vs leader",
      render: (c) => {
        const g = gapVsLeader(c, r.noise_s)
        return <span className={g.measurable === false ? "warn-text" : undefined}>{g.text}</span>
      },
    },
    { key: "entry", header: "Entry", render: (c) => balanceCell(c.balance, "entry") },
    { key: "mid", header: "Mid", render: (c) => balanceCell(c.balance, "mid") },
    { key: "exit", header: "Exit", render: (c) => balanceCell(c.balance, "exit") },
    { key: "dist", header: "From neutral", align: "right", title: "Summed distance from neutral over the three phases", render: (c) => balanceDistance(c.balance) },
    {
      key: "base",
      header: "",
      render: (c) =>
        result.duel_id != null ? (
          <button className={c.rank === 1 ? "primary" : "ghost"} onClick={() => onBaseline({ duel_id: result.duel_id!, winner_key: c.key, name: c.name })} data-testid={`make-baseline-${c.rank}`}>
            Make baseline
          </button>
        ) : null,
    },
  ]
  return (
    <div className="stack" data-testid="duel-result">
      <p className="verdict" data-testid="duel-verdict">
        {verdict(r)}
      </p>
      {!r.same_session && (
        <p className="not-comparable" data-testid="cross-session">
          {r.callouts.find((t) => t.startsWith("Laps come from different sessions")) ?? "Laps come from different sessions."} The noise band is widened to {fmt(r.noise_s, 2)} s.
        </p>
      )}
      <DataTable columns={columns} rows={r.contestants} rowKey={(c) => c.key} testId="duel-table" rowClass={(c) => (c.rank === 1 ? "leader-row" : undefined)} />
      <p className="note">
        Compared on {result.condition?.compound_label} · {result.condition?.state} track · noise band {fmt(r.noise_s, 2)} s per lap
        {result.correction ? ` · fuel ${fmt(result.correction.fuel_s_per_kg * 1000, 0)} ms/kg, tyre age ${fmt(result.correction.deg_s_per_lap, 3)} s/lap (${result.correction.deg_source})` : ""}
        . Feel is only available in a live duel.
      </p>
      {r.cost_note && <p className={`note${r.cost_source === "fallback" ? " warn-text" : ""}`}>{r.cost_note}</p>}
      {result.balance_note && <p className="note warn-text">Balance not measured: {result.balance_note}</p>}
      {r.callouts.length > 0 && (
        <ul className="callouts" data-testid="duel-callouts">
          {r.callouts.filter((t) => r.same_session || !t.startsWith("Laps come from different sessions")).map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function DuelPanel({ track, picked, setups, onBaseline }: { track: string; picked: string[]; setups: SetupCandidate[]; onBaseline: MakeBaseline }) {
  const duel = useRunDuel(track)
  const names = picked.map((fp) => setups.find((s) => s.fingerprint === fp)).filter((s): s is SetupCandidate => !!s).map(setupLabel)
  const result = duel.data
  return (
    <Panel
      title="Duel"
      testId="duel-panel"
      actions={
        <>
          <span className="dim">{pickHint(picked.length)}</span>
          <button className="primary" disabled={!canRank(picked) || duel.isPending} onClick={() => duel.mutate(picked)} data-testid="rank-button">
            {duel.isPending ? "Ranking…" : "Rank them"}
          </button>
        </>
      }
    >
      {picked.length > 0 && <p className="note">Picked: {names.join(" · ")}</p>}
      {duel.isError && <ErrorBox error={duel.error} />}
      {result && !result.comparable && (
        <div className="not-comparable" data-testid="not-comparable">
          <b>Not comparable</b>
          <ul>
            {result.reasons.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          <p className="note">Setups are compared on clean laps of the same track condition and compound, at least {result.min_clean_laps} each.</p>
        </div>
      )}
      {result?.comparable && <ResultTable result={result} onBaseline={onBaseline} />}
      {!result && !duel.isPending && <p className="note">Ranks on 70 % race pace (fuel- and tyre-age-corrected, plus what its tyre wear costs over a 50 % race) and 30 % one-lap pace. Differences inside the noise are called a tie and balance decides.</p>}
    </Panel>
  )
}

export function SetupsPage() {
  const params = useParams()
  const track = params.track ?? ""
  const navigate = useNavigate()
  const catalog = useTrackCatalog()
  const setups = useTrackSetups(track)
  const baseline = useTrackBaseline(track)
  const setBaseline = useSetBaseline(track)
  const [picked, setPicked] = useState<string[]>([])
  useEffect(() => setPicked([]), [track])

  const raced = (catalog.data?.tracks ?? []).filter((t) => t.sessions > 0)
  const list = setups.data?.setups ?? []

  return (
    <div className="stack" data-testid="setups-page">
      <div className="page-head">
        <h1>Setups · {track}</h1>
        <label className="field inline">
          Track
          <select value={track} onChange={(e) => navigate(`/track/${encodeURIComponent(e.target.value)}/setups`)} aria-label="Track">
            {!raced.some((t) => t.track === track) && <option value={track}>{track}</option>}
            {raced.map((t) => (
              <option key={t.track} value={t.track}>
                {t.track}
              </option>
            ))}
          </select>
        </label>
      </div>
      <BaselineCard track={track} baseline={baseline.data} loading={baseline.isLoading} error={baseline.error} saveError={setBaseline.error} onRestore={(id) => setBaseline.mutate({ restore_id: id })} />
      <Panel title="Setups driven here" testId="setup-list">
        {setups.isLoading && <Loading what="Reading the track's runs…" />}
        {setups.isError && <ErrorBox error={setups.error} />}
        {setups.data && list.length === 0 && <p className="note">No setups driven on this track in the library yet.</p>}
        {list.length > 0 && <p className="note">Distinct mechanical setups (fuel and tyre pressures do not count). Tick two or three to rank them, click a name to rename.</p>}
        {list.map((s) => (
          <SetupCard key={s.fingerprint} setup={s} track={track} picked={picked.includes(s.fingerprint)} onToggle={() => setPicked((p) => togglePick(p, s.fingerprint))} onBaseline={(b) => setBaseline.mutate(b)} />
        ))}
      </Panel>
      {list.length > 0 && <DuelPanel track={track} picked={picked} setups={list} onBaseline={(b) => setBaseline.mutate(b)} />}
    </div>
  )
}
