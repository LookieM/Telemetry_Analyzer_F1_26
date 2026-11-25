import { jsx as _jsx } from "react/jsx-runtime";
/**
 * Stacked uPlot panes with one shared cursor, drag-zoom on every pane, double-click reset, bands (corners / stints),
 * dashed markers (pit / box), a live legend per pane and click-to-pin. Port of telemetry/ui/assets/trace_chart.js;
 * the cursor now travels through the zustand cursor store (group = `sync`) instead of window events.
 */
import { useEffect, useId, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { selectGroup, useCursorStore } from "../lib/cursor";
import { fmt } from "../lib/format";
import "./TraceChart.css";
function readTheme(el) {
    const css = getComputedStyle(el);
    const v = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
    return {
        text: v("--text", "#d8dde3"),
        dim: v("--text-dim", "#8a93a0"),
        grid: v("--grid", "rgba(128,128,128,0.18)"),
        border: v("--border", "rgba(128,128,128,0.45)"),
        band: v("--band", "rgba(128,128,128,0.10)"),
        accent: v("--accent", "#e03c31"),
        font: v("--font-ui", "sans-serif"),
    };
}
function drawBands(u, data, theme, labels) {
    const bands = data.bands ?? [];
    if (!bands.length)
        return;
    const ctx = u.ctx;
    const { top, height } = u.bbox;
    const dpr = devicePixelRatio || 1;
    ctx.save();
    bands.forEach((b, i) => {
        const x0 = u.valToPos(b.from, "x", true);
        const x1 = u.valToPos(b.to, "x", true);
        if (x1 < u.bbox.left || x0 > u.bbox.left + u.bbox.width)
            return;
        ctx.globalAlpha = b.color ? 0.14 : i % 2 ? 0 : 0.55;
        ctx.fillStyle = b.color || theme.band;
        ctx.fillRect(x0, top, x1 - x0, height);
        if (labels && b.label && x1 - x0 > 18 * dpr) {
            ctx.globalAlpha = 0.9;
            ctx.fillStyle = theme.dim;
            ctx.font = `600 ${10 * dpr}px ${theme.font}`;
            ctx.fillText(b.label, x0 + 3 * dpr, top + 11 * dpr);
        }
    });
    ctx.restore();
}
function vline(u, x, color, dash, width) {
    const px = u.valToPos(x, "x", true);
    if (!Number.isFinite(px) || px < u.bbox.left || px > u.bbox.left + u.bbox.width)
        return null;
    const ctx = u.ctx;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = width * (devicePixelRatio || 1);
    ctx.setLineDash(dash);
    ctx.beginPath();
    ctx.moveTo(px, u.bbox.top);
    ctx.lineTo(px, u.bbox.top + u.bbox.height);
    ctx.stroke();
    ctx.restore();
    return px;
}
function drawOverlay(u, data, theme, pinned, labels) {
    const dpr = devicePixelRatio || 1;
    for (const m of data.markers ?? []) {
        const px = vline(u, m.x, m.color || theme.border, [4 * dpr, 3 * dpr], 1);
        if (px != null && labels && m.label) {
            const ctx = u.ctx;
            ctx.save();
            ctx.fillStyle = m.color || theme.text;
            ctx.font = `${10 * dpr}px ${theme.font}`;
            ctx.fillText(m.label, px + 3 * dpr, u.bbox.top + u.bbox.height - 4 * dpr);
            ctx.restore();
        }
    }
    if (pinned != null)
        vline(u, pinned, theme.accent, [], 1.5);
}
function seriesOpts(s, paneDecimals, theme) {
    const o = {
        label: s.label,
        stroke: s.color || theme.text,
        width: s.width ?? 1.5,
        spanGaps: false,
        value: (_u, v) => fmt(v, s.decimals ?? paneDecimals),
        points: { show: false },
    };
    if (s.dash)
        o.dash = [6, 4];
    if (s.mode === "points") {
        o.paths = () => null;
        const c = s.color || theme.text;
        o.points = { show: true, size: s.size ?? 6, fill: s.hollow ? "rgba(0,0,0,0)" : c, stroke: c, width: s.hollow ? 1.5 : 1 };
    }
    else if (s.mode === "step") {
        o.paths = uPlot.paths.stepped?.({ align: 1 });
    }
    return o;
}
function buildPane(host, pane, index, last, data, theme, width, sync, id, built) {
    const wrap = document.createElement("div");
    wrap.className = "tc-pane";
    const head = document.createElement("div");
    head.className = "tc-head";
    head.textContent = pane.unit ? `${pane.title} · ${pane.unit}` : pane.title;
    wrap.appendChild(head);
    host.appendChild(wrap);
    const dec = pane.decimals ?? 1;
    const isLast = index === last;
    const axisFont = `11px ${theme.font}`;
    const opts = {
        width,
        height: pane.height || 150,
        padding: [6, 10, 0, 0],
        scales: { x: { time: false }, y: pane.range ? { range: pane.range } : {} },
        series: [
            { label: data.xLabel || "Distance (m)", value: (_u, v) => fmt(v, data.xDecimals ?? 0) },
            ...pane.series.map((s) => seriesOpts(s, dec, theme)),
        ],
        axes: [
            {
                stroke: theme.dim,
                font: axisFont,
                grid: { stroke: theme.grid, width: 1 },
                ticks: { stroke: theme.grid, width: 1, size: 4 },
                size: isLast ? 30 : 8,
                values: isLast ? undefined : (_u, vals) => vals.map(() => ""),
            },
            {
                stroke: theme.dim,
                font: axisFont,
                grid: { stroke: theme.grid, width: 1 },
                ticks: { stroke: theme.grid, width: 1, size: 4 },
                size: 58,
                values: (_u, vals) => vals.map((v) => fmt(v, pane.axisDecimals ?? 0)),
            },
        ],
        cursor: {
            sync: { key: `tc-${sync}-${id}`, setSeries: false },
            drag: { x: true, y: false, setScale: true, dist: 5 },
            points: { size: 6 },
        },
        legend: { show: true, live: true },
        hooks: {
            drawClear: [(u) => drawBands(u, data, theme, index === 0)],
            draw: [(u) => drawOverlay(u, data, theme, built.pinned, index === 0)],
            setCursor: [
                (u) => {
                    if (index !== 0 || built.external)
                        return;
                    const left = u.cursor.left;
                    const x = left != null && left >= 0 ? u.posToVal(left, "x") : null;
                    useCursorStore.getState().setHover(sync, x, id);
                },
            ],
            setScale: [
                (u, key) => {
                    if (key !== "x" || built.syncing)
                        return;
                    built.syncing = true;
                    const { min, max } = u.scales.x;
                    for (const p of built.plots) {
                        if (p !== u && (p.scales.x.min !== min || p.scales.x.max !== max))
                            p.setScale("x", { min: min, max: max });
                    }
                    built.syncing = false;
                },
            ],
        },
    };
    const u = new uPlot(opts, [data.x, ...pane.series.map((s) => s.values)], wrap);
    u.over.addEventListener("mousedown", (e) => {
        built.down = e.clientX;
    });
    u.over.addEventListener("mouseup", (e) => {
        if (built.down != null && Math.abs(e.clientX - built.down) < 4 && u.cursor.left != null && u.cursor.left >= 0) {
            const v = u.posToVal(u.cursor.left, "x");
            if (Number.isFinite(v))
                useCursorStore.getState().setPinned(sync, v);
        }
        built.down = null;
    });
    return u;
}
/** Move every pane's cursor to x (or hide it); the move is not echoed back into the store. */
function applyExternal(built, x) {
    built.external = true;
    try {
        for (const u of built.plots) {
            if (x == null) {
                u.setCursor({ left: -10, top: -10 });
                continue;
            }
            const left = u.valToPos(x, "x");
            const inside = Number.isFinite(left) && left >= 0 && left <= u.bbox.width / (devicePixelRatio || 1);
            u.setCursor(inside ? { left, top: Math.max(1, u.bbox.height / (2 * (devicePixelRatio || 1))) } : { left: -10, top: -10 });
        }
    }
    finally {
        built.external = false;
    }
}
/** Set the x window of every pane (the panes keep each other in sync); no window = the full data range. */
function applyZoom(built, data, zoom) {
    const first = data.x[0];
    const last = data.x[data.x.length - 1];
    const [min, max] = zoom ?? [first, last];
    const lead = built.plots[0];
    if (lead && Number.isFinite(min) && Number.isFinite(max) && max > min)
        lead.setScale("x", { min, max });
}
export function TraceChart({ data, sync, testId, zoom = null }) {
    const hostRef = useRef(null);
    const builtRef = useRef(null);
    const zoomRef = useRef(zoom);
    zoomRef.current = zoom;
    const zoomFrom = zoom?.[0];
    const zoomTo = zoom?.[1];
    const id = useId();
    useEffect(() => {
        const host = hostRef.current;
        if (!host)
            return;
        host.textContent = "";
        if (!data.x.length || !data.panes.length) {
            const empty = document.createElement("div");
            empty.className = "tc-empty";
            empty.textContent = data.emptyText || "No data for this chart.";
            host.appendChild(empty);
            return;
        }
        const chartTheme = readTheme(host);
        const built = {
            plots: [],
            pinned: useCursorStore.getState().groups[sync]?.pinnedX ?? null,
            syncing: false,
            down: null,
            external: false,
        };
        const width = Math.max(320, host.clientWidth || 900);
        const last = data.panes.length - 1;
        data.panes.forEach((pane, i) => built.plots.push(buildPane(host, pane, i, last, data, chartTheme, width, sync, id, built)));
        builtRef.current = built;
        if (zoomRef.current)
            applyZoom(built, data, zoomRef.current);
        const observer = new ResizeObserver(() => {
            const w = Math.max(320, host.clientWidth);
            for (const p of built.plots)
                if (Math.abs(p.width - w) > 1)
                    p.setSize({ width: w, height: p.height });
        });
        observer.observe(host);
        const unsubscribe = useCursorStore.subscribe((state, prev) => {
            const cur = selectGroup(sync)(state);
            const before = selectGroup(sync)(prev);
            if (cur.pinnedX !== before.pinnedX) {
                built.pinned = cur.pinnedX;
                built.plots.forEach((p) => p.redraw(false));
            }
            if ((cur.hoverX !== before.hoverX || cur.hoverSource !== before.hoverSource) && cur.hoverSource !== id)
                applyExternal(built, cur.hoverX);
        });
        return () => {
            unsubscribe();
            observer.disconnect();
            built.plots.forEach((p) => p.destroy());
            built.plots = [];
            builtRef.current = null;
        };
    }, [data, sync, id]);
    useEffect(() => {
        const built = builtRef.current;
        if (built && built.plots.length)
            applyZoom(built, data, zoomFrom != null && zoomTo != null ? [zoomFrom, zoomTo] : null);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [zoomFrom, zoomTo]);
    return _jsx("div", { ref: hostRef, className: "tc-root", "data-testid": testId ?? "trace-chart" });
}
