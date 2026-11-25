import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { CAR_LAYOUT, tempColor } from "../lib/colors";
import { fmt } from "../lib/format";
import "./CarGrid.css";
function num(v) {
    return typeof v === "number" && Number.isFinite(v) ? v : null;
}
export function CarGrid({ row, targets, wearRate }) {
    return (_jsxs("div", { children: [_jsx("div", { className: "cg-grid", "data-testid": "car-grid", children: CAR_LAYOUT.map((w) => {
                    const t = num(row[`T_${w}`]);
                    const target = w === "FL" || w === "FR" ? targets.hot_front_psi : targets.hot_rear_psi;
                    return (_jsxs("div", { className: "cg-card", style: { borderLeftColor: tempColor(t, targets.temp_lo, targets.temp_hi) }, children: [_jsx("div", { className: "cg-wheel", children: w }), _jsxs("div", { className: "cg-temp", children: [fmt(t, 0), " \u00B0C"] }), _jsxs("div", { className: "cg-detail", children: ["peak ", fmt(num(row[`Tpk_${w}`]), 0), " \u00B0C \u00B7 in window ", fmt(num(row[`Twin_${w}`]), 0), "%", _jsx("br", {}), fmt(num(row[`P_${w}`]), 1), " psi", target ? _jsxs("span", { className: "dim", children: [" (target ", target.toFixed(1), ")"] }) : null, _jsx("br", {}), "wear ", fmt(num(row[`W_${w}`]), 1), "% \u00B7 ", fmt(wearRate[w], 2), " %/lap this stint"] })] }, w));
                }) }), _jsxs("p", { className: "note", children: ["Colour = lap-mean temperature vs the ", targets.temp_lo.toFixed(0), "\u2013", targets.temp_hi.toFixed(0), " \u00B0C window (blue cold \u00B7 green in window \u00B7 red hot)."] })] }));
}
