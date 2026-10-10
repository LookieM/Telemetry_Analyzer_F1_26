import { useEffect, useMemo } from "react"
import { Link } from "react-router-dom"
import { formatLapTime, fmt, fmtSigned } from "../lib/format"
import { ERS_MODES, compoundColor, gapLabel, useLive } from "../lib/live"
import type { LiveRival, LiveSnapshot, LiveStrategy, LiveWheel } from "../lib/live"
import "./Live.css"

const LAYOUT: ("FL" | "FR" | "RL" | "RR")[] = ["FL", "FR", "RL", "RR"]

function Bar({ value, max, color, label, warn }: { value: number; max: number; color?: string; label?: string; warn?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className="lv-bar">
      <div className="lv-bar-fill" style={{ width: `${pct}%`, background: color }} />
      {warn != null && <div className="lv-bar-mark" style={{ left: `${Math.min(100, (warn / max) * 100)}%` }} />}
      {label && <span className="lv-bar-label">{label}</span>}
    </div>
  )
}

function DeltaTrace({ points, ref_ }: { points: [number, number][]; ref_: string | null }) {
  const W = 1000
  const H = 200
  if (points.length < 2) return <div className="lv-trace lv-empty">Delta trace starts after the first metres{ref_ ? "" : " (no reference lap yet)"}</div>
  const xs = points.map((p) => p[0])
  const ys = points.map((p) => p[1])
  const xMax = Math.max(...xs, 1)
  const lim = Math.max(0.5, Math.min(5, Math.max(...ys.map(Math.abs))))
  const sx = (x: number) => (x / xMax) * W
  const sy = (y: number) => H / 2 - (Math.max(-lim, Math.min(lim, y)) / lim) * (H / 2 - 6)
  const d = points.map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ")
  const last = points[points.length - 1]
  return (
    <svg className="lv-trace" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Delta over distance">
      <rect x="0" y="0" width={W} height={H / 2} className="lv-trace-slow" />
      <rect x="0" y={H / 2} width={W} height={H / 2} className="lv-trace-fast" />
      <line x1="0" x2={W} y1={H / 2} y2={H / 2} className="lv-trace-zero" />
      <path d={d} className="lv-trace-line" vectorEffect="non-scaling-stroke" />
      <circle cx={sx(last[0])} cy={sy(last[1])} r="6" className="lv-trace-dot" />
      <text x="8" y="22" className="lv-trace-lbl">
        +{lim.toFixed(1)} s slower
      </text>
      <text x="8" y={H - 8} className="lv-trace-lbl">
        −{lim.toFixed(1)} s faster
      </text>
    </svg>
  )
}

function Wheel({ name, w, limit }: { name: string; w: LiveWheel; limit: number }) {
  return (
    <div className={`lv-wheel st-${w.status} wear-${w.wear_status}`} data-testid={`wheel-${name}`}>
      <div className="lv-wheel-head">
        <b>{name}</b>
        <span>{w.press_psi.toFixed(1)} psi</span>
      </div>
      <div className="lv-wheel-temps">
        <span className={`t t-${w.status}`}>{w.surface}°</span>
        <span className={`t t-${w.inner_status} sm`}>{w.inner}° in</span>
      </div>
      <Bar value={w.wear ?? 0} max={100} warn={limit} color={w.wear_status === "ok" ? "var(--good)" : w.wear_status === "high" ? "var(--warn)" : "var(--bad)"} label={w.wear != null ? `${w.wear.toFixed(0)}%` : "—"} />
      {(w.blister ?? 0) > 0 && <div className="lv-blister">blister {w.blister}%</div>}
    </div>
  )
}

function StrategyCard({ s, session }: { s: LiveStrategy | null; session: LiveSnapshot["session"] }) {
  if (!s) return <div className="lv-card lv-strategy lv-muted">{session.type === "Race" ? "Strategy call starts after the first lap." : "Strategy runs in races only."}</div>
  if (!s.available) return <div className="lv-card lv-strategy lv-muted">{s.reason ?? "No strategy model available."}</div>
  const under = session.sc > 0
  const call = s.call ?? s.call_green
  const inWindow = s.box_window ? session.lap >= s.box_window[0] && session.lap <= s.box_window[1] + 1 : false
  return (
    <div className={`lv-card lv-strategy call-${(call ?? "").toLowerCase()}`} data-testid="strategy-card">
      <div className="lv-call">
        <span className="lv-call-word">{call}</span>
        <span className="lv-call-sub">{under ? "under SC" : "green"}</span>
      </div>
      <div className="lv-strat-grid">
        <div>
          <span className="k">Window</span>
          <b>{s.box_window ? `lap ${s.box_window[0]}–${s.box_window[1]}` : "—"}</b>
          {inWindow && <span className="tag">open</span>}
        </div>
        <div>
          <span className="k">Fit</span>
          <b>{s.fit_label ?? "—"}</b>
        </div>
        <div>
          <span className="k">Box vs stay</span>
          <b>{s.box_now_s != null && s.stay_out_s != null && Number.isFinite(s.stay_out_s) ? fmtSigned(s.box_now_s - s.stay_out_s, 1) + " s" : "forced"}</b>
        </div>
        <div>
          <span className="k">Under SC</span>
          <b>{s.call_sc}</b>
        </div>
      </div>
    </div>
  )
}

function Rivals({ rows }: { rows: LiveRival[] }) {
  return (
    <table className="lv-rivals" data-testid="rivals">
      <thead>
        <tr>
          <th>P</th>
          <th>Driver</th>
          <th>Gap</th>
          <th>Tyre</th>
          <th>Stops</th>
          <th>Last</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.pos} className={`${r.you ? "you" : ""} ${r.threat ? "threat" : ""}`}>
            <td>{r.pos}</td>
            <td>
              {r.name}
              {r.in_pit && <span className="tag">PIT</span>}
              {r.threat && <span className="tag bad">undercut</span>}
            </td>
            <td>{r.you ? "—" : gapLabel(r.gap_s)}</td>
            <td>
              <span className="chip" style={{ background: compoundColor(r.compound) }} />
              {r.label ?? "—"} <span className="dim">{r.age ?? "—"}L</span>
            </td>
            <td>{r.stops}</td>
            <td>{formatLapTime(r.last)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function LivePage() {
  const live = useLive()
  const s = live.snapshot
  useEffect(() => {
    document.title = "Live — Telemetria"
  }, [])
  const stale = useMemo(() => live.socket !== "open" || !live.status?.connected, [live.socket, live.status])
  const conn = live.socket !== "open" ? "Server offline — reconnecting…" : !live.status?.connected ? "Waiting for the game (UDP)…" : null

  return (
    <div className="live" data-testid="live-page">
      <header className="lv-bar-top">
        <Link to="/" className="lv-back" title="Back to the library">
          ←
        </Link>
        {s ? (
          <>
            <b className="lv-track">{s.session.track}</b>
            <span>{s.session.type}</span>
            <span className="lv-lap">
              Lap <b>{s.session.lap}</b>
              {s.session.total_laps ? `/${s.session.total_laps}` : ""}
            </span>
            <span className="lv-pos">
              P<b>{s.session.position}</b>
            </span>
            {s.session.sc > 0 && <span className="lv-flag sc">{s.session.sc_name}</span>}
            {s.session.pit_status > 0 && <span className="lv-flag pit">PIT</span>}
            {s.timing.invalid && <span className="lv-flag bad">INVALID</span>}
            {s.session.penalties_s > 0 && <span className="lv-flag bad">+{s.session.penalties_s}s</span>}
            <span className="lv-spacer" />
            <span>{s.session.weather}</span>
            <span className="dim">
              {s.session.air_temp}° / {s.session.track_temp}°
            </span>
            {s.session.forecast.some((f) => f.rain_pct >= 40) && <span className="lv-flag warn">rain {Math.max(...s.session.forecast.map((f) => f.rain_pct))}%</span>}
          </>
        ) : (
          <b className="lv-track">Live</b>
        )}
        <span className={`lv-conn ${stale ? "off" : "on"}`} title={`${live.status?.packets_per_s ?? 0} pkt/s, ${live.status?.frame_gap_pct ?? 0}% lost`}>
          {stale ? "●" : "●"}
        </span>
      </header>

      {!s ? (
        <div className="lv-wait" data-testid="live-wait">
          <h1>{conn ?? "Waiting for telemetry…"}</h1>
          <p className="dim">Game: Settings → Telemetry → UDP On, IP 127.0.0.1, port 20777. Or run <code>python -m telemetria_server.replay data/udp_captures/&lt;file&gt;.f1cap</code>.</p>
        </div>
      ) : (
        <>
          {conn && <div className="lv-conn-banner">{conn}</div>}
          <section className="lv-timing">
            <div className={`lv-delta ${s.timing.delta == null ? "" : s.timing.delta <= 0 ? "fast" : "slow"}`} data-testid="delta">
              <span className="lv-delta-val">{s.timing.delta == null ? "—" : fmtSigned(s.timing.delta, 2)}</span>
              <span className="lv-delta-ref">vs {s.timing.ref ?? "no reference"}</span>
            </div>
            <div className="lv-times">
              <div>
                <span className="k">Lap</span>
                <b>{formatLapTime(s.timing.lap_time)}</b>
              </div>
              <div>
                <span className="k">Predicted</span>
                <b>{formatLapTime(s.timing.predicted)}</b>
              </div>
              <div>
                <span className="k">Last</span>
                <b>{formatLapTime(s.timing.last)}</b>
              </div>
              <div>
                <span className="k">Best</span>
                <b>{formatLapTime(s.timing.best)}</b>
              </div>
              <div className="lv-sectors">
                {[0, 1].map((i) => (
                  <span key={i} className={s.timing.sector - 1 === i ? "cur" : ""}>
                    S{i + 1} {formatLapTime(s.timing.sectors[i])}
                  </span>
                ))}
              </div>
            </div>
          </section>

          <section className="lv-card lv-tracecard">
            <DeltaTrace points={live.deltaTrace} ref_={s.timing.ref} />
          </section>

          <section className="lv-tyres">
            <div className="lv-tyre-head">
              <span className="chip big" style={{ background: compoundColor(s.tyres.compound) }} />
              <b>{s.tyres.label}</b>
              <span className="dim">{s.tyres.age} laps old · limit {s.tyres.wear_limit.toFixed(0)}%</span>
            </div>
            <div className="lv-wheels">
              {LAYOUT.map((n) => (
                <Wheel key={n} name={n} w={s.tyres.wheels[n]} limit={s.tyres.wear_limit} />
              ))}
            </div>
          </section>

          <section className="lv-energy">
            <div className="lv-card">
              <h3>Fuel</h3>
              <Bar value={s.fuel.kg} max={s.fuel.capacity || 110} color="var(--info)" label={`${s.fuel.kg.toFixed(1)} kg`} />
              <div className="lv-kv">
                <span>
                  per lap <b>{fmt(s.fuel.per_lap, 2)}</b>
                </span>
                <span>
                  laps left <b>{fmt(s.fuel.laps_left, 1)}</b>
                </span>
                <span className={s.fuel.margin_laps != null && s.fuel.margin_laps < 0 ? "bad" : ""}>
                  margin <b>{fmtSigned(s.fuel.margin_laps, 1)}</b>
                </span>
              </div>
            </div>
            <div className="lv-card">
              <h3>
                ERS · {ERS_MODES[s.ers.mode] ?? s.ers.mode}
                {s.ers.overtake && <span className="tag good">OVERTAKE</span>}
                {s.ers.active_aero === 1 && <span className="tag">X-mode</span>}
              </h3>
              <Bar value={s.ers.store_mj} max={4} color="var(--warn)" label={`${s.ers.store_mj.toFixed(2)} MJ`} />
              <div className="lv-kv">
                <span>
                  deployed <b>{s.ers.deployed_mj.toFixed(2)}</b>
                </span>
                <span>
                  harvested <b>{s.ers.harvested_mj.toFixed(2)}</b>
                </span>
                <span>
                  limit <b>{s.ers.harvest_limit_mj.toFixed(1)}</b>
                </span>
              </div>
            </div>
          </section>

          <StrategyCard s={s.strategy} session={s.session} />

          <section className="lv-card lv-rivalcard">
            <Rivals rows={s.rivals} />
          </section>

          <footer className="lv-events">
            {live.events.length === 0 ? <span className="dim">No events yet</span> : live.events.map((e, i) => <span key={`${e.t}-${i}`} className={`ev ev-${e.kind}`}>{e.text}</span>)}
          </footer>
        </>
      )}
    </div>
  )
}
