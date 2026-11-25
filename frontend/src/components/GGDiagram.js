import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/** Traction circle of one lap (SVG): lateral vs longitudinal g, points coloured by speed; follows the shared lap cursor. */
import { useMemo } from "react";
import { scaleColor, scaleGradient } from "../lib/colors";
import { selectGroup, useCursorStore } from "../lib/cursor";
import { nearestPoint, SPEED_SCALE } from "../lib/gg";
import "./GGDiagram.css";
const SIZE = 400;
const PAD = 28;
export function GGDiagram({ data, sync = "lap" }) {
    const cursor = useCursorStore(selectGroup(sync));
    const half = (SIZE - 2 * PAD) / 2;
    const c = SIZE / 2;
    const px = (g) => c + (g / data.limit) * half;
    const py = (g) => c - (g / data.limit) * half; // braking (negative) at the bottom
    const span = Math.max(1e-9, data.speedMax - data.speedMin);
    const dots = useMemo(() => data.points.map((p, i) => (_jsx("circle", { cx: px(p.lat), cy: py(p.long), r: 1.8, fill: (p.speed != null && scaleColor(SPEED_SCALE, (p.speed - data.speedMin) / span)) || "var(--text-dim)" }, i))), 
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data]);
    const rings = [];
    for (let g = 0.5; g <= data.limit + 1e-9; g += 0.5)
        rings.push(g);
    const at = nearestPoint(data.points, cursor.hoverX ?? cursor.pinnedX);
    const here = at >= 0 ? data.points[at] : null;
    return (_jsxs("div", { className: "gg", "data-testid": "gg-diagram", children: [_jsxs("svg", { viewBox: `0 0 ${SIZE} ${SIZE}`, role: "img", "aria-label": "G-G diagram", children: [rings.map((g) => (_jsx("circle", { className: Number.isInteger(g) ? "gg-ring major" : "gg-ring", cx: c, cy: c, r: (g / data.limit) * half }, g))), _jsx("line", { className: "gg-axis", x1: PAD, x2: SIZE - PAD, y1: c, y2: c }), _jsx("line", { className: "gg-axis", x1: c, x2: c, y1: PAD, y2: SIZE - PAD }), _jsx("text", { className: "gg-label", x: c + 4, y: PAD - 8, children: "accel" }), _jsx("text", { className: "gg-label", x: c + 4, y: SIZE - PAD + 18, children: "brake" }), _jsxs("text", { className: "gg-label", x: SIZE - PAD, y: c - 6, textAnchor: "end", children: [data.limit.toFixed(1), " g"] }), dots, here && _jsx("circle", { className: "gg-cursor", cx: px(here.lat), cy: py(here.long), r: 7 })] }), _jsxs("div", { className: "gg-foot", children: [_jsx("span", { className: "gg-scale", style: { background: scaleGradient(SPEED_SCALE) } }), _jsxs("span", { className: "note", children: [data.speedMin.toFixed(0), "\u2013", data.speedMax.toFixed(0), " km/h \u00B7 peak lateral ", data.peaks.lat.toFixed(2), " g \u00B7 braking ", data.peaks.brake.toFixed(2), " g \u00B7 traction ", data.peaks.accel.toFixed(2), " g", here ? ` · at ${here.x.toFixed(0)} m: ${here.lat.toFixed(2)} / ${here.long.toFixed(2)} g` : ""] })] })] }));
}
