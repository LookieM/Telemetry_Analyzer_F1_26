import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import "./StintTimeline.css";
export function StintTimeline({ rows, lapsTotal, showAxis = true }) {
    const total = Math.max(1, lapsTotal);
    const step = total > 40 ? 10 : 5;
    const ticks = [];
    for (let lap = step; lap < total; lap += step)
        ticks.push(lap);
    return (_jsxs("div", { className: "st-root", "data-testid": "stint-timeline", children: [rows.map((row) => (_jsxs("div", { className: "st-row", children: [_jsx("div", { className: "st-label", title: row.label, children: row.label }), _jsx("div", { className: "st-track", children: row.stints.map((s, i) => {
                            const laps = Math.max(0, s.to - s.from + 1);
                            return (_jsx("div", { className: `st-seg${s.light ? " st-light" : ""}`, style: { flexGrow: laps, flexBasis: 0, background: s.color }, title: s.title || `${s.text} L${s.from}–${s.to} (${laps} laps)`, "data-testid": "stint-segment", children: _jsx("span", { className: "st-text", children: laps >= total * 0.06 ? `${s.text} ${laps}` : "" }) }, i));
                        }) }), _jsx("div", { className: "st-note", children: row.note ?? "" })] }, row.label))), showAxis && (_jsxs("div", { className: "st-row st-axis-row", children: [_jsx("div", { className: "st-label" }), _jsx("div", { className: "st-track st-axis", children: ticks.map((lap) => (_jsx("span", { className: "st-tick", style: { left: `${(lap / total) * 100}%` }, children: lap }, lap))) }), _jsxs("div", { className: "st-note", children: [total, " laps"] })] }))] }));
}
