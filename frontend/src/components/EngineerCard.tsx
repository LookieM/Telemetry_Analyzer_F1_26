/** Live page: the race engineer card (optometrist-style setup test). All decisions are server-side; this renders the view. */
import { useState } from "react"
import { ApiError, baselineApi, engineerApi } from "../api/client"
import type { EngineerHistoryRow, EngineerResult, EngineerVariant, EngineerView } from "../api/types"
import { engineerBaselineName, offerSummary } from "../lib/baseline"
import { MAX_TAGS, PHASE_LABEL, buildAnswer, commandError, confidenceLabel, cornerRowLine, engineerPanel, fmtBudget, fmtDelta, stopwatchLine, tagCheckLine, tagLabel, toggleTag, validateAnswer, variantValue } from "../lib/engineer"
import "./EngineerCard.css"

type Run = (fn: () => Promise<EngineerView>) => Promise<void>

function Start({ run, busy }: { run: Run; busy: boolean }) {
  return (
    <div className="eg-start" data-testid="eg-start">
      <p className="dim">Optometrist-style setup test for practice: you drive two variants, say which felt better, it checks the stopwatch.</p>
      <div className="eg-verdict two">
        <button type="button" className="eg-big" disabled={busy} onClick={() => void run(() => engineerApi.start("short"))} data-testid="eg-start-short">
          Short<small>≈ 18 min · 1 parameter</small>
        </button>
        <button type="button" className="eg-big" disabled={busy} onClick={() => void run(() => engineerApi.start("full"))} data-testid="eg-start-full">
          Full<small>≈ 50 min · 3 parameters</small>
        </button>
      </div>
    </div>
  )
}

function Result({ r }: { r: EngineerResult }) {
  const roles = r.roles
  return (
    <div className="eg-result" data-testid="eg-result">
      <div className={`eg-sw ${r.measurable ? (r.stopwatch_winner === "2" ? "v2" : "v1") : "none"}`}>
        <b>{stopwatchLine(r)}</b>
        <span className="dim">
          {confidenceLabel(r.confidence)} · laps {r.n["1"]} vs {r.n["2"]}
          {r.deg_s_per_lap != null ? ` · tyre wear correction ${fmtDelta(r.deg_s_per_lap, 3)} s/lap` : ""}
        </span>
      </div>
      {r.sectors.length > 0 && (
        <div className="eg-sectors">
          {r.sectors.map((s) => (
            <span key={s.sector} className={s.delta_s < 0 ? "fast" : "slow"}>
              S{s.sector} <b>{fmtDelta(s.delta_s, 3)}</b>
            </span>
          ))}
          <span className="dim">(variant 2 minus 1)</span>
        </div>
      )}
      {!!r.corners?.length && (
        <div className="eg-corners" data-testid="eg-corners">
          {r.corners.map((c) => (
            <div key={`${c.corner}-${c.phase}`} className={c.delta_s < 0 ? "fast" : "slow"}>
              {cornerRowLine(c)}
            </div>
          ))}
          <span className="dim">(variant 2 minus 1)</span>
        </div>
      )}
      {!!r.tag_check?.length && (
        <div className="eg-tagcheck" data-testid="eg-tagcheck">
          {r.tag_check.map((t) => {
            const l = tagCheckLine(t)
            return (
              <div key={t.tag} className={l.cls}>
                {l.mark} {l.text}
              </div>
            )
          })}
        </div>
      )}
      {r.agreement_text && <div className={`eg-agree ${r.agreement ?? ""}`}>{r.agreement_text}</div>}
      {roles && (
        <div className="eg-roles dim">
          Variant 1 was the <b>{roles["1"] ?? "?"}</b>, Variant 2 the <b>{roles["2"] ?? "?"}</b>
        </div>
      )}
    </div>
  )
}

function QuestionForm({ v, run, busy }: { v: EngineerView; run: Run; busy: boolean }) {
  const [verdict, setVerdict] = useState<"1" | "2" | "same" | null>(null)
  const [strength, setStrength] = useState<"slight" | "clear">("clear")
  const [tags, setTags] = useState<string[]>([])
  const [note, setNote] = useState("")
  const problem = validateAnswer({ verdict, strength, tags }, v.question.tags)
  const label = v.param?.label ?? "this pair"
  return (
    <div className="eg-question" data-testid="eg-question">
      <div className="eg-q-title">
        Back in the garage: which felt better{v.param ? ` (${label})` : ""}?
      </div>
      <div className="eg-verdict">
        {(["1", "2", "same"] as const).map((x) => (
          <button key={x} type="button" className={`eg-big ${verdict === x ? "on" : ""}`} onClick={() => setVerdict(x)} aria-pressed={verdict === x} data-testid={`eg-v-${x}`}>
            {x === "same" ? "Same" : x}
            {x !== "same" && v.variant_text && <small>{variantValue(v, x)}</small>}
          </button>
        ))}
      </div>
      <div className="eg-strength" role="group" aria-label="Strength">
        {(["slight", "clear"] as const).map((x) => (
          <button key={x} type="button" className={`eg-seg ${strength === x ? "on" : ""}`} onClick={() => setStrength(x)} aria-pressed={strength === x} data-testid={`eg-s-${x}`}>
            {x === "slight" ? "Slightly" : "Clearly"}
          </button>
        ))}
        <span className="dim eg-count">
          tags {tags.length}/{MAX_TAGS}
        </span>
      </div>
      <div className="eg-tags" data-testid="eg-tags">
        {v.question.tags.map((t) => {
          const on = tags.includes(t)
          const full = !on && tags.length >= MAX_TAGS
          return (
            <button key={t} type="button" className={`eg-tag ${on ? "on" : ""}`} disabled={full} onClick={() => setTags(toggleTag(tags, t))} aria-pressed={on}>
              {tagLabel(t)}
            </button>
          )
        })}
      </div>
      <div className="eg-submit">
        <input className="eg-note" type="text" placeholder="Optional note (what you felt)" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} aria-label="Note" />
        <button type="button" className="eg-go" disabled={busy || problem != null} title={problem ?? "Send your answer"} onClick={() => verdict && void run(() => engineerApi.answer(buildAnswer({ verdict, strength, tags, note })))} data-testid="eg-submit">
          Submit
        </button>
      </div>
      {problem && verdict == null && <div className="dim eg-hint">{problem}</div>}
    </div>
  )
}

function Confirm({ v, run, busy }: { v: EngineerView; run: Run; busy: boolean }) {
  const proposed = v.question.proposed
  const roles = v.last_result?.roles
  return (
    <div className="eg-confirm" data-testid="eg-confirm">
      {v.last_result && <Result r={v.last_result} />}
      <div className="eg-q-title">Which variant becomes the new baseline?</div>
      <div className="eg-verdict two">
        {(["1", "2"] as EngineerVariant[]).map((x) => (
          <button key={x} type="button" className={`eg-big ${proposed === x ? "on" : ""}`} disabled={busy} onClick={() => void run(() => engineerApi.confirm(x))} data-testid={`eg-confirm-${x}`}>
            Keep {x}
            <small>
              {variantValue(v, x)}
              {roles?.[x] ? ` · ${roles[x]}` : ""}
              {proposed === x ? " · your answer" : ""}
            </small>
          </button>
        ))}
      </div>
    </div>
  )
}

function Revert({ v, run, busy }: { v: EngineerView; run: Run; busy: boolean }) {
  const r = v.revert_proposal!
  return (
    <div className="eg-revert" data-testid="eg-revert">
      <div className="eg-q-title">Parc fermé: revert {r.label}?</div>
      <p>{r.text}</p>
      <div className="eg-verdict two">
        <button type="button" className="eg-big on" disabled={busy} onClick={() => void run(() => engineerApi.revert(true))} data-testid="eg-revert-yes">
          Revert to {String(r.to)}
        </button>
        <button type="button" className="eg-big" disabled={busy} onClick={() => void run(() => engineerApi.revert(false))} data-testid="eg-revert-no">
          Keep {String(r.from)}
        </button>
      </div>
    </div>
  )
}

function RunPanel({ v }: { v: EngineerView }) {
  const r = v.run
  const quali = v.phase === "quali"
  return (
    <div className="eg-run" data-testid="eg-run">
      <div className="eg-instruction" data-testid="eg-instruction">
        {v.instruction ?? "Waiting for the next instruction…"}
      </div>
      {v.variant_text && (
        <div className="eg-variants">
          {(["1", "2"] as EngineerVariant[]).map((x) => (
            <div key={x} className={`eg-var ${r.variant === x ? "now" : ""} ${v.detected.variant === x ? "det" : ""}`}>
              <span className="eg-var-n">{x}</span>
              <span className="eg-var-t">{variantValue(v, x)}</span>
              <span className="eg-var-c">
                {r.counted[x]}/{r.target}
              </span>
              {r.variant === x && <span className="tag good">drive now</span>}
              {v.detected.variant === x && <span className="tag">on car</span>}
            </div>
          ))}
        </div>
      )}
      <div className="eg-progress">
        {r.variant ? (
          <>
            Variant <b>{r.variant}</b>: lap <b>{Math.min(r.lap + 1, r.target)}</b> of {r.target}
          </>
        ) : quali ? (
          "Quali laps counted"
        ) : (
          "Back to the garage"
        )}
        {!v.in_garage ? <span className="dim"> · on track</span> : <span className="dim"> · in garage</span>}
      </div>
      {v.detected.warning && <div className="eg-warn" data-testid="eg-warning">{v.detected.warning}</div>}
      {v.tyre_hint && <div className="eg-hint">{v.tyre_hint}</div>}
    </div>
  )
}

function BaselineOffer({ v }: { v: EngineerView }) {
  const offer = v.baseline_offer
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle")
  if (!offer || !v.track) return null
  const make = async () => {
    setState("busy")
    try {
      await baselineApi.set(v.track!, { setup: offer.final, source: "engineer", name: engineerBaselineName() })
      setState("done")
    } catch {
      setState("error")
    }
  }
  return (
    <div className="eg-offer" data-testid="eg-offer">
      <div className="eg-hint">Changed in this test: {offerSummary(offer)}</div>
      {state === "done" ? (
        <div className="eg-hint" data-testid="eg-offer-done">Saved as the {v.track} baseline (see the Setups page).</div>
      ) : (
        <button type="button" className="eg-ctl" disabled={state === "busy"} onClick={() => void make()} data-testid="eg-make-baseline">
          Make this the track baseline
        </button>
      )}
      {state === "error" && <div className="eg-error" role="alert">Could not save the baseline</div>}
    </div>
  )
}

function LongRun({ v }: { v: EngineerView }) {
  const lr = v.long_run
  const laps = lr?.laps ?? []
  return (
    <div className="eg-long" data-testid="eg-long">
      <div className="eg-instruction">{v.instruction ?? (v.phase === "done" ? "Program finished" : "Long run")}</div>
      {lr && (
        <>
          <div className="eg-progress">
            {lr.label ?? "Race compound"}: <b>{laps.length}</b> of {lr.target} laps
            {lr.wear_pct_per_lap != null && (
              <>
                {" "}
                · wear <b>{lr.wear_pct_per_lap.toFixed(1)}%</b>/lap
              </>
            )}
            {lr.pace_deg_s_per_lap != null && (
              <>
                {" "}
                · pace <b>{fmtDelta(lr.pace_deg_s_per_lap, 3)}</b> s/lap
              </>
            )}
          </div>
          {laps.length > 0 && (
            <table className="eg-laps">
              <thead>
                <tr>
                  <th>Lap</th>
                  <th>Time</th>
                  <th>Fuel-corr.</th>
                  <th>Wear</th>
                </tr>
              </thead>
              <tbody>
                {laps.slice(-6).map((l) => (
                  <tr key={l.lap}>
                    <td>{l.lap}</td>
                    <td>{l.time_s != null ? l.time_s.toFixed(3) : "—"}</td>
                    <td>{l.corrected_s != null ? l.corrected_s.toFixed(3) : "—"}</td>
                    <td>{l.wear_pct != null ? `${l.wear_pct.toFixed(0)}%` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

function History({ rows, settled }: { rows: EngineerHistoryRow[]; settled: EngineerView["settled"] }) {
  const done = Object.values(settled)
  if (!rows.length && !done.length) return null
  return (
    <details className="eg-history" data-testid="eg-history">
      <summary>
        History · {rows.length} {rows.length === 1 ? "pair" : "pairs"}
        {done.length > 0 && <span className="dim"> · settled: {done.map((s) => `${s.label} ${s.value}`).join(", ")}</span>}
      </summary>
      <ul>
        {rows.map((h) => (
          <li key={h.n}>
            <b>{h.label}</b>{" "}
            {h.variants ? Object.values(h.variants).join(" vs ") : ""} →{" "}
            {h.outcome === "skipped" ? "skipped" : h.winner ? `${h.winner_role ?? `variant ${h.winner}`} won` : h.outcome}
            {h.delta_s != null && <span className="dim"> · {fmtDelta(h.delta_s, 3)} s/lap</span>}
            {h.your_answer && <span className="dim"> · you: {h.your_answer.verdict === "same" ? "same" : `variant ${h.your_answer.verdict}`}</span>}
          </li>
        ))}
      </ul>
    </details>
  )
}

export function EngineerCard({ view }: { view: EngineerView | null | undefined }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run: Run = async (fn) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(commandError(e instanceof ApiError ? e.status : null, e instanceof Error ? e.message : String(e)))
    } finally {
      setBusy(false)
    }
  }
  const panel = engineerPanel(view)
  const v = view && view.phase !== "idle" ? view : null
  const active = v != null && v.phase !== "done"

  return (
    <section className={`lv-card eg-card panel-${panel}`} data-testid="engineer-card">
      <div className="eg-head">
        <h3>Race engineer</h3>
        {v && (
          <>
            <span className="eg-phase" data-testid="eg-phase">
              {PHASE_LABEL[v.phase] ?? v.phase}
            </span>
            {v.param && v.phase === "balance" && (
              <span className="eg-param">
                {v.param.label} <span className="dim">({v.param.index} of {v.param.of})</span>
              </span>
            )}
            <span className="lv-spacer" />
            {active && (
              <span className="eg-budget" title="Time left in this program" data-testid="eg-budget">
                {fmtBudget(v.budget.left_s)} left
              </span>
            )}
          </>
        )}
      </div>

      {panel === "start" && <Start busy={busy} run={run} />}
      {panel === "revert" && v && <Revert v={v} run={run} busy={busy} />}
      {panel === "confirm" && v && <Confirm v={v} run={run} busy={busy} />}
      {panel === "question" && v && <QuestionForm key={v.history.length} v={v} run={run} busy={busy} />}
      {(panel === "run" || panel === "quali") && v && <RunPanel v={v} />}
      {(panel === "long_run" || panel === "done") && v && <LongRun v={v} />}
      {panel === "done" && v && <BaselineOffer v={v} />}
      {panel === "done" && <Start busy={busy} run={run} />}

      {error && (
        <div className="eg-error" role="alert" data-testid="eg-error">
          {error}
        </div>
      )}

      {v && v.feed.length > 0 && (
        <ul className="eg-feed" data-testid="eg-feed">
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
      {v && <History rows={v.history} settled={v.settled} />}

      {v && (
        <div className="eg-controls">
          {active && v.phase === "balance" && (
            <button type="button" className="eg-ctl" disabled={busy} onClick={() => void run(engineerApi.skip)} data-testid="eg-skip">
              Skip parameter
            </button>
          )}
          {active && (
            <button type="button" className="eg-ctl" disabled={busy} onClick={() => void run(engineerApi.nextPhase)} data-testid="eg-next">
              Next phase
            </button>
          )}
          <span className="lv-spacer" />
          {active && (
            <button type="button" className="eg-ctl stop" disabled={busy} onClick={() => void run(engineerApi.stop)} data-testid="eg-stop">
              Stop
            </button>
          )}
        </div>
      )}
    </section>
  )
}
