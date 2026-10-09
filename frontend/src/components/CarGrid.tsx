/** FL FR / RL RR cards: lap-mean temperature vs the operating window, peak, hot pressure, wear. */
import type { Targets, WheelMap, WheelRow } from "../api/types"
import { CAR_LAYOUT, tempColor } from "../lib/colors"
import { fmt } from "../lib/format"
import "./CarGrid.css"

interface Props {
  row: WheelRow
  targets: Targets
  wearRate: WheelMap
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

export function CarGrid({ row, targets, wearRate }: Props) {
  return (
    <div>
      <div className="cg-grid" data-testid="car-grid">
        {CAR_LAYOUT.map((w) => {
          const t = num(row[`T_${w}`])
          const target = w === "FL" || w === "FR" ? targets.hot_front_psi : targets.hot_rear_psi
          return (
            <div className="cg-card" key={w} style={{ borderLeftColor: tempColor(t, targets.temp_lo, targets.temp_hi) }}>
              <div className="cg-wheel">{w}</div>
              <div className="cg-temp">{fmt(t, 0)} °C</div>
              <div className="cg-detail">
                peak {fmt(num(row[`Tpk_${w}`]), 0)} °C · in window {fmt(num(row[`Twin_${w}`]), 0)}%
                <br />
                {fmt(num(row[`P_${w}`]), 1)} psi{target ? <span className="dim"> (target {target.toFixed(1)})</span> : null}
                <br />
                wear {fmt(num(row[`W_${w}`]), 1)}% · {fmt(wearRate[w], 2)} %/lap this stint
              </div>
            </div>
          )
        })}
      </div>
      <p className="note">
        Colour = lap-mean temperature vs the {targets.temp_lo.toFixed(0)}–{targets.temp_hi.toFixed(0)} °C window (blue cold · green in window · red hot).
      </p>
    </div>
  )
}
