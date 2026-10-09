/** Stint bars per strategy / session: segments sized by laps, coloured by compound. Port of stint_timeline.js. */
import type { StintRow } from "../lib/traces"
import "./StintTimeline.css"

export interface TimelineRow {
  label: string
  stints: StintRow[]
  note?: string
}

interface Props {
  rows: TimelineRow[]
  lapsTotal: number
  showAxis?: boolean
}

export function StintTimeline({ rows, lapsTotal, showAxis = true }: Props) {
  const total = Math.max(1, lapsTotal)
  const step = total > 40 ? 10 : 5
  const ticks: number[] = []
  for (let lap = step; lap < total; lap += step) ticks.push(lap)
  return (
    <div className="st-root" data-testid="stint-timeline">
      {rows.map((row) => (
        <div className="st-row" key={row.label}>
          <div className="st-label" title={row.label}>
            {row.label}
          </div>
          <div className="st-track">
            {row.stints.map((s, i) => {
              const laps = Math.max(0, s.to - s.from + 1)
              return (
                <div
                  key={i}
                  className={`st-seg${s.light ? " st-light" : ""}`}
                  style={{ flexGrow: laps, flexBasis: 0, background: s.color }}
                  title={s.title || `${s.text} L${s.from}–${s.to} (${laps} laps)`}
                  data-testid="stint-segment"
                >
                  <span className="st-text">{laps >= total * 0.06 ? `${s.text} ${laps}` : ""}</span>
                </div>
              )
            })}
          </div>
          <div className="st-note">{row.note ?? ""}</div>
        </div>
      ))}
      {showAxis && (
        <div className="st-row st-axis-row">
          <div className="st-label" />
          <div className="st-track st-axis">
            {ticks.map((lap) => (
              <span className="st-tick" key={lap} style={{ left: `${(lap / total) * 100}%` }}>
                {lap}
              </span>
            ))}
          </div>
          <div className="st-note">{total} laps</div>
        </div>
      )}
    </div>
  )
}
