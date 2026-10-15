import type { Lockup, Phase } from "../api/types"
import { PHASES, isSpinning, lockupSummary, lockupText, type BalanceColumn } from "../lib/balance"
import { fmt } from "../lib/format"
import "./BalanceStrip.css"

const PHASE_LABEL: Record<Phase, string> = { entry: "Entry", mid: "Mid", exit: "Exit" }

interface Props {
  columns: BalanceColumn[]
  selectedId: number | null
  onSelect: (id: number) => void
  lockups: Lockup[]
  /** Rear slip on exit (traction) row; hidden when false. */
  showTraction?: boolean
}

/** Phase x corner heat strip of the understeer index (colour relative to the typical car) with a traction row and the lock-up list. */
export function BalanceStrip({ columns, selectedId, onSelect, lockups, showTraction = true }: Props) {
  return (
    <div data-testid="balance-strip">
      <div className="table-wrap">
        <table className="bal-grid">
          <thead>
            <tr>
              <th />
              {columns.map((c) => (
                <th key={c.id} className={c.id === selectedId ? "sel" : undefined} onClick={() => onSelect(c.id)}>
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {PHASES.map((p) => (
              <tr key={p}>
                <th scope="row">{PHASE_LABEL[p]}</th>
                {columns.map((c) => {
                  const cell = c.phases[p]
                  return (
                    <td
                      key={c.id}
                      className={`bal-cell${c.id === selectedId ? " sel" : ""}`}
                      style={cell.color ? { background: cell.color } : undefined}
                      title={cell.value == null ? "Not enough cornering samples" : `${c.name} ${p}: ${cell.label}, index ${fmt(cell.value, 1)}° (${fmt(cell.rel, 1)}° vs the typical car)`}
                      onClick={() => onSelect(c.id)}
                    >
                      {cell.value == null ? "–" : fmt(cell.value, 1)}
                    </td>
                  )
                })}
              </tr>
            ))}
            {showTraction && (
              <tr>
                <th scope="row" title="Mean rear wheel slip ratio on the throttle after the apex; high = the rear spins up">Exit rear slip</th>
                {columns.map((c) => (
                  <td key={c.id} className={`bal-trac${isSpinning(c.traction) ? " spin" : ""}${c.id === selectedId ? " sel" : ""}`} onClick={() => onSelect(c.id)}>
                    {c.traction == null ? "–" : fmt(c.traction * 100, 0) + "%"}
                  </td>
                ))}
              </tr>
            )}
            <tr>
              <th scope="row">Lock-ups</th>
              {columns.map((c) => {
                const n = Object.entries(c.lockups)
                return (
                  <td key={c.id} className={`bal-lock${c.id === selectedId ? " sel" : ""}`} onClick={() => onSelect(c.id)}>
                    {n.length ? n.map(([w, k]) => `${w}${k > 1 ? `×${k}` : ""}`).join(" ") : ""}
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
      </div>
      <div className="bal-legend">
        <span className="bal-key" style={{ background: "#3E7CC9" }} /> oversteer
        <span className="bal-key" style={{ background: "#4A4F57" }} /> like the typical car
        <span className="bal-key" style={{ background: "#E08A1E" }} /> understeer
        <span className="note">Values: front minus rear slip angle in degrees; colours are relative to the typical car of each phase.</span>
      </div>
      <div className="bal-lockups" data-testid="lockup-list">
        <strong>Lock-ups: {lockupSummary(lockups)}</strong>
        {lockups.length > 0 && (
          <ul>
            {lockups.slice(0, 12).map((l, i) => (
              <li key={i}>{lockupText(l)}</li>
            ))}
            {lockups.length > 12 && <li>… and {lockups.length - 12} more</li>}
          </ul>
        )}
      </div>
    </div>
  )
}
