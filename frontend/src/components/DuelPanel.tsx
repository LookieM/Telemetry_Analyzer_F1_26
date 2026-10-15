/** Live page: the setup duel inside the Engineer card (start form, run panel, feel ranking, ranking table, confirm). */
import { useState } from "react"
import { duelApi } from "../api/client"
import type { LiveDuelContestant, LiveDuelRanking, LiveDuelView } from "../api/types"
import { balanceCell, balanceDistance, gapVsLeader, verdict, wearText } from "../lib/duel"
import { ORDINAL, assignRank, duelNames, duelPanel, feelOrder, finishedText, labelOf, lapsText, statusText, validateFeel } from "../lib/duelLive"
import { formatLapTime } from "../lib/format"
import "./DuelPanel.css"

export type DuelRun = (fn: () => Promise<unknown>) => Promise<void>

export function DuelStart({ run, busy }: { run: DuelRun; busy: boolean }) {
  const [n, setN] = useState<2 | 3>(2)
  const [names, setNames] = useState<string[]>(["", "", ""])
  return (
    <div className="dl-start" data-testid="dl-start">
      <div className="dl-start-title">Setup duel</div>
      <p className="dim">Rank 2 or 3 complete setups on your own laps (race pace, tyre wear, balance). Name them if you like.</p>
      <div className="dl-n">
        {([2, 3] as const).map((k) => (
          <button key={k} type="button" className={`eg-seg ${n === k ? "on" : ""}`} onClick={() => setN(k)} data-testid={`dl-n-${k}`}>
            {k} setups
          </button>
        ))}
      </div>
      <div className="dl-names">
        {Array.from({ length: n }, (_, i) => (
          <input
            key={i}
            className="eg-note"
            maxLength={40}
            placeholder={`Setup ${"ABC"[i]} name (optional)`}
            value={names[i]}
            onChange={(e) => setNames((p) => p.map((x, j) => (j === i ? e.target.value : x)))}
            data-testid={`dl-name-${i}`}
          />
        ))}
      </div>
      <button type="button" className="eg-ctl dl-go" disabled={busy} onClick={() => void run(() => duelApi.start(n, duelNames(names, n)))} data-testid="dl-start-btn">
        Start duel
      </button>
    </div>
  )
}

function ContestantRow({ c, v }: { c: LiveDuelContestant; v: LiveDuelView }) {
  return (
    <div className={`dl-row ${v.next === c.key ? "now" : ""} ${c.skipped ? "skipped" : ""}`} data-testid={`dl-row-${c.key}`}>
      <span className="dl-key">{c.key}</span>
      <span className="dl-label">{c.label}</span>
      <span className="dl-laps" data-testid={`dl-laps-${c.key}`}>
        {lapsText(c)}
      </span>
      <span className={`tag ${c.on_car ? "good" : ""}`}>{statusText(c, v)}</span>
      <span className="dl-times dim">{c.last_s != null ? `last ${formatLapTime(c.last_s)}` : ""}</span>
    </div>
  )
}

function RunPanel({ v }: { v: LiveDuelView }) {
  return (
    <div className="eg-run" data-testid="dl-run">
      <div className="eg-instruction" data-testid="dl-instruction">
        {v.instruction}
      </div>
      <div className="dl-rows">
        {v.contestants.map((c) => (
          <ContestantRow key={c.key} c={c} v={v} />
        ))}
      </div>
      <div className="eg-progress">
        {v.compound_label ? (
          <>
            Compound <b>{v.compound_label}</b>
          </>
        ) : (
          "Compound set by the first counted lap"
        )}
        <span className="dim">
          {" "}
          · {v.min_laps} laps needed, {v.target} wanted, max {v.max_laps} · {v.in_garage ? "in garage" : "on track"}
        </span>
      </div>
      {v.detected.warning && (
        <div className="eg-warn" data-testid="dl-warning">
          {v.detected.warning}
        </div>
      )}
      {v.tyre_hint && <div className="eg-hint">{v.tyre_hint}</div>}
    </div>
  )
}

function FeelForm({ v, run, busy }: { v: LiveDuelView; run: DuelRun; busy: boolean }) {
  const keys = v.question.keys
  const [ranks, setRanks] = useState<Record<string, number>>({})
  const [note, setNote] = useState("")
  const problem = validateFeel(ranks, keys)
  const order = feelOrder(ranks, keys)
  return (
    <div className="dl-feel" data-testid="dl-feel">
      <div className="eg-q-title">Which setup felt best? Rank them before you see the numbers.</div>
      {keys.map((k) => (
        <div key={k} className="dl-feel-row">
          <span className="dl-key">{k}</span>
          <span className="dl-label">{labelOf(v, k)}</span>
          <span className="dl-places">
            {keys.map((_, i) => (
              <button key={i} type="button" className={`eg-seg ${ranks[k] === i + 1 ? "on" : ""}`} onClick={() => setRanks((r) => assignRank(r, k, i + 1))} data-testid={`dl-feel-${k}-${i + 1}`}>
                {ORDINAL[i]}
              </button>
            ))}
          </span>
        </div>
      ))}
      <div className="eg-submit">
        <input className="eg-note" maxLength={500} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} data-testid="dl-feel-note" />
        <button type="button" className="eg-go" disabled={busy || problem != null} title={problem ?? undefined} onClick={() => order && void run(() => duelApi.rank(order, note.trim() || undefined))} data-testid="dl-feel-send">
          Rank
        </button>
      </div>
      {problem && <div className="eg-hint">{problem}</div>}
    </div>
  )
}

function RankingTable({ v, r }: { v: LiveDuelView; r: LiveDuelRanking }) {
  return (
    <div className="dl-result" data-testid="dl-result">
      <p className="dl-verdict" data-testid="dl-verdict">
        {verdict(r)}
      </p>
      <table className="eg-laps dl-table" data-testid="dl-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Setup</th>
            <th>Race</th>
            <th>Lap</th>
            <th>Wear</th>
            <th>Gap</th>
          </tr>
        </thead>
        <tbody>
          {r.contestants.map((c) => (
            <tr key={c.key} className={c.rank === 1 ? "leader" : ""}>
              <td>{c.rank}</td>
              <td>
                <b>{c.name}</b>
                <div className="dim dl-bal">
                  entry {balanceCell(c.balance, "entry")} · mid {balanceCell(c.balance, "mid")} · exit {balanceCell(c.balance, "exit")} · off neutral {balanceDistance(c.balance)}
                </div>
              </td>
              <td>{formatLapTime(c.race_pace_s)}</td>
              <td>{formatLapTime(c.quali_pace_s)}</td>
              <td>{wearText(c.wear_pct_per_lap)}</td>
              <td>{gapVsLeader(c, r.noise_s).text}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="eg-hint">
        70 % race pace (with wear cost) + 30 % one lap · noise band {r.noise_s.toFixed(2)} s/lap · {r.cost_note}
        {v.feel && (
          <>
            {" "}
            · your feel: {v.feel.order.map((k) => labelOf(v, k)).join(" > ")}
            {v.feel.note ? ` ("${v.feel.note}")` : ""}
          </>
        )}
      </div>
      {r.callouts.length > 0 && (
        <ul className="dl-callouts" data-testid="dl-callouts">
          {r.callouts.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Review({ v, run, busy }: { v: LiveDuelView; run: DuelRun; busy: boolean }) {
  const r = v.ranking!
  const live = v.contestants.filter((c) => !c.skipped)
  return (
    <div className="dl-review" data-testid="dl-review">
      <RankingTable v={v} r={r} />
      <div className="eg-q-title">Which setup becomes the track baseline?</div>
      <div className={`eg-verdict ${live.length === 3 ? "" : "two"}`}>
        {live.map((c) => (
          <button key={c.key} type="button" className={`eg-big ${r.proposed === c.key ? "on" : ""}`} disabled={busy} onClick={() => void run(() => duelApi.confirm(c.key))} data-testid={`dl-confirm-${c.key}`}>
            {c.label}
            <small>{r.proposed === c.key ? "ranked first" : "your call"}</small>
          </button>
        ))}
      </div>
    </div>
  )
}

export function DuelPanel({ v, run, busy }: { v: LiveDuelView; run: DuelRun; busy: boolean }) {
  const panel = duelPanel(v)
  const active = v.phase === "running" || v.phase === "review"
  return (
    <>
      {panel === "run" && <RunPanel v={v} />}
      {panel === "feel" && (
        <>
          <RunPanel v={v} />
          <FeelForm v={v} run={run} busy={busy} />
        </>
      )}
      {panel === "review" && <Review v={v} run={run} busy={busy} />}
      {panel === "done" && (
        <div data-testid="dl-done">
          <div className="eg-instruction">{finishedText(v)}</div>
          {v.ranking && <RankingTable v={v} r={v.ranking} />}
        </div>
      )}
      {v.feed.length > 0 && (
        <ul className="eg-feed" data-testid="dl-feed">
          {v.feed
            .slice(-5)
            .reverse()
            .map((f, i) => (
              <li key={`${f.t}-${i}`} className={i === 0 ? "new" : ""}>
                {f.text}
              </li>
            ))}
        </ul>
      )}
      <div className="eg-controls">
        {v.phase === "running" && (
          <button type="button" className="eg-ctl" disabled={busy} onClick={() => void run(duelApi.skip)} data-testid="dl-skip">
            Skip next setup
          </button>
        )}
        <span className="lv-spacer" />
        {active && (
          <button type="button" className="eg-ctl stop" disabled={busy} onClick={() => void run(duelApi.stop)} data-testid="dl-stop">
            Stop duel
          </button>
        )}
      </div>
    </>
  )
}
