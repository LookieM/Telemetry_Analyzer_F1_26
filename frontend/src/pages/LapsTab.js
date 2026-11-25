import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from "react";
import { useCompare, useLapChannels, useLapExtras, useMap } from "../api/hooks";
import { LapSelect, ReferenceFields, useReference } from "../components/ReferencePicker";
import { GGDiagram } from "../components/GGDiagram";
import { TraceChart } from "../components/TraceChart";
import { TrackMap } from "../components/TrackMap";
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel } from "../components/ui";
import { selectGroup, useCursorStore } from "../lib/cursor";
import { fmt, fmtSigned, formatLapTime } from "../lib/format";
import { bestLapNumber } from "../lib/sessions";
import { compareTrace, cornerBands, driverTrace, sessionPaceTrace, TRACE_CHANNELS } from "../lib/traces";
import { buildGG, GG_CHANNELS, GG_EXTRAS } from "../lib/gg";
import { loadExtras, saveExtras, usableExtras } from "../lib/extras";
const COLORS = ["speed", "throttle", "brake", "gear", "delta"];
function sectorColumns(kind, name) {
    return [
        { key: "n", header: name, align: "right", render: (r) => r[kind] },
        { key: "from", header: "From (m)", align: "right", render: (r) => fmt(r.dist_start, 0) },
        { key: "to", header: "To (m)", align: "right", render: (r) => fmt(r.dist_end, 0) },
        { key: "d", header: "Δ (s)", align: "right", render: (r) => _jsx("span", { className: r.delta_s > 0 ? "bad" : "good", children: fmtSigned(r.delta_s, 3) }) },
        { key: "c", header: "Cumulative (s)", align: "right", render: (r) => fmtSigned(r.delta_end, 3) },
    ];
}
export function LapsTab({ detail, focusLap, setFocusLap }) {
    const { session, laps } = detail;
    const resetCursor = useCursorStore((s) => s.reset);
    const cursor = useCursorStore(selectGroup("lap"));
    const best = bestLapNumber(laps);
    const choice = useReference(detail, "none");
    const { mode, selection } = choice;
    const [color, setColor] = useState("speed");
    useEffect(() => {
        resetCursor("lap");
        return () => resetCursor("lap");
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [session.id]);
    const ref = useMemo(() => {
        if (!selection)
            return null;
        if (selection.session != null)
            return selection;
        return selection.lap === focusLap ? null : selection;
    }, [selection, focusLap]);
    const mapColor = color === "delta" && !ref ? "speed" : color;
    const map = useMap(session.id, focusLap, ref?.lap ?? null, ref?.session ?? null, mapColor);
    const extrasInfo = useLapExtras(session.id);
    const [picked, setPicked] = useState(loadExtras);
    const extras = useMemo(() => usableExtras(picked, extrasInfo.data), [picked, extrasInfo.data]);
    const togglePicked = (key) => {
        const next = picked.includes(key) ? picked.filter((k) => k !== key) : [...picked, key];
        setPicked(next);
        saveExtras(next);
    };
    const cmp = useCompare(session.id, focusLap, ref?.lap ?? null, ref?.session ?? null, !!ref, extras);
    const single = useLapChannels(session.id, focusLap, TRACE_CHANNELS, !ref, extras);
    const ggAvailable = !!extrasInfo.data && GG_EXTRAS.every((k) => extrasInfo.data.find((e) => e.key === k)?.available);
    const ggChannels = useLapChannels(session.id, focusLap, GG_CHANNELS, ggAvailable, GG_EXTRAS);
    const gg = useMemo(() => buildGG(ggChannels.data), [ggChannels.data]);
    const paceData = useMemo(() => sessionPaceTrace(laps), [laps]);
    const labels = useMemo(() => ({ cmp: `L${focusLap}`, ref: ref ? (ref.session ? `S${ref.session} L${ref.lap}` : `L${ref.lap}`) : "Ref" }), [focusLap, ref]);
    // Keyed by content so a map refetch (e.g. new colour) does not rebuild the traces and lose the zoom.
    const spansKey = JSON.stringify(map.data?.spans ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const bands = useMemo(() => cornerBands(map.data?.spans), [spansKey]);
    const traceData = useMemo(() => {
        if (ref) {
            if (!cmp.data)
                return null;
            return { ...compareTrace(cmp.data, labels, 115, extras), bands };
        }
        if (!single.data)
            return null;
        return { ...driverTrace(single.data, labels, 115, extras), bands };
    }, [ref, cmp.data, single.data, labels, bands, extras]);
    const focus = laps.find((l) => l.lap === focusLap);
    const cursorX = cursor.hoverX ?? cursor.pinnedX;
    const cornerHere = cursorX != null ? map.data?.spans.find((s) => cursorX >= s.from && cursorX <= s.to)?.name : undefined;
    const lapColumns = [
        { key: "lap", header: "Lap", align: "right", render: (l) => l.lap },
        { key: "class", header: "Class", render: (l) => l.lap_class },
        { key: "time", header: "Time", align: "right", render: (l) => formatLapTime(l.lap_time) },
        { key: "delta", header: "Δ best", align: "right", render: (l) => fmtSigned(l.delta_best, 3) },
        { key: "vmax", header: "Vmax", align: "right", render: (l) => fmt(l.vmax, 1) },
        { key: "full", header: "Full thr %", align: "right", render: (l) => fmt(l.throttle_full_pct, 1) },
        { key: "coast", header: "Coast %", align: "right", render: (l) => fmt(l.coast_pct, 1) },
        { key: "fuel", header: "Fuel used", align: "right", render: (l) => fmt(l.fuel_used, 2) },
        { key: "wear", header: "Wear avg %", align: "right", render: (l) => fmt(l.tyre_wear_avg, 1) },
        { key: "comp", header: "Compound", render: (l) => l.compound_label ?? "—" },
        { key: "lock", header: "Lockups", align: "right", render: (l) => fmt(l.lockup_samples, 0) },
    ];
    return (_jsxs("div", { className: "stack", "data-testid": "laps-tab", children: [_jsxs(Panel, { className: "toolbar", children: [_jsxs("div", { className: "row", children: [_jsx(LapSelect, { laps: laps, value: focusLap, onChange: setFocusLap, label: "Focus lap" }), _jsx(ReferenceFields, { choice: choice, modes: ["none", "lap", "session"] }), _jsxs("label", { className: "field", children: ["Map colour", _jsx("select", { value: color, onChange: (e) => setColor(e.target.value), "aria-label": "Map colour", children: COLORS.map((c) => (_jsx("option", { value: c, disabled: c === "delta" && !ref, children: c }, c))) })] })] }), extrasInfo.data && (_jsxs("div", { className: "row extras", role: "group", "aria-label": "Extra channels", "data-testid": "extras-picker", children: [_jsx("span", { className: "toolbar-label", children: "Extra panes" }), extrasInfo.data.map((e) => (_jsxs("label", { className: `field extra${e.available && picked.includes(e.key) ? " on" : ""}${e.available ? "" : " off"}`, title: e.available ? undefined : (e.reason ?? "Not available"), children: [_jsx("input", { type: "checkbox", checked: e.available && picked.includes(e.key), disabled: !e.available, onChange: () => togglePicked(e.key) }), e.label, !e.available && _jsxs("span", { className: "note", children: [" (", e.reason, ")"] })] }, e.key)))] })), mode === "lap" && !ref && _jsx("p", { className: "note", children: "Pick a different reference lap to see deltas and overlays." })] }), _jsxs(MetricRow, { children: [_jsx(Metric, { label: "Focus lap", value: formatLapTime(focus?.lap_time), sub: focus ? `${fmtSigned(focus.delta_best, 3)} s vs best` : "", testId: "metric-focus" }), _jsx(Metric, { label: "Best lap", value: `#${best ?? "—"} · ${formatLapTime(session.best_lap_time)}` }), _jsx(Metric, { label: "Vmax", value: focus?.vmax != null ? `${focus.vmax.toFixed(1)} km/h` : "—" }), _jsx(Metric, { label: "Cursor", value: cursorX != null ? `${cursorX.toFixed(0)} m` : "—", sub: cursor.pinnedX != null && cursor.hoverX == null ? "pinned" : "", testId: "metric-cursor" }), _jsx(Metric, { label: "At corner", value: cornerHere ?? "—" }), ref && cmp.data && (_jsx(Metric, { label: "Lap \u0394 vs reference", value: _jsxs("span", { className: cmp.data.final_delta != null && cmp.data.final_delta > 0 ? "bad" : "good", children: [fmtSigned(cmp.data.final_delta, 3), " s"] }), sub: cmp.data.final_delta != null && cmp.data.final_delta > 0 ? "slower" : "faster", testId: "metric-delta" }))] }), _jsxs("div", { className: "grid-2", children: [_jsxs(Panel, { title: `${session.track ?? "Track"} — lap ${focusLap ?? "?"}${ref ? ` vs ${labels.ref}` : ""}`, children: [map.isLoading && _jsx(Loading, { what: "Loading map\u2026" }), map.isError && _jsx(ErrorBox, { error: map.error }), map.data && _jsx(TrackMap, { data: map.data, sync: "lap", height: 560 })] }), _jsxs(Panel, { title: "Driver trace", children: [(ref ? cmp.isLoading : single.isLoading) && _jsx(Loading, { what: "Loading channels\u2026" }), (ref ? cmp.isError : single.isError) && _jsx(ErrorBox, { error: ref ? cmp.error : single.error }), traceData && _jsx(TraceChart, { data: traceData, sync: "lap", testId: "driver-trace" }), _jsx("p", { className: "note", children: "Drag on a trace to zoom every pane \u00B7 double-click to reset \u00B7 click to pin the cursor." })] })] }), ref && cmp.data && (_jsxs("div", { className: "grid-2", children: [_jsx(Panel, { title: "Sector deltas", children: _jsx(DataTable, { columns: sectorColumns("sector", "Sector"), rows: cmp.data.sectors, rowKey: (r) => r.sector ?? 0, testId: "sector-table" }) }), _jsx(Panel, { title: "Mini-sector deltas", children: _jsx(DataTable, { columns: sectorColumns("mini_sector", "Mini"), rows: cmp.data.mini_sectors, rowKey: (r) => r.mini_sector ?? 0, maxHeight: 300, testId: "mini-sector-table" }) })] })), _jsxs("div", { className: "grid-2", children: [_jsxs(Panel, { title: "Session pace", testId: "session-pace", children: [_jsx(TraceChart, { data: paceData, sync: "pace", testId: "session-pace-chart" }), _jsx("p", { className: "note", children: "Every lap of the session: best, push and other laps (out / in / SC / slow); fuel used and average tyre wear per lap." })] }), _jsx(Panel, { title: `G-G · lap ${focusLap ?? "?"}`, testId: "gg-panel", children: !extrasInfo.data || (ggAvailable && ggChannels.isLoading) ? (_jsx(Loading, { what: "Loading g-forces\u2026" })) : !ggAvailable ? (_jsx("p", { className: "note", children: "No g-force channels in this export." })) : ggChannels.isError ? (_jsx(ErrorBox, { error: ggChannels.error })) : gg ? (_jsx(GGDiagram, { data: gg })) : (_jsx("p", { className: "note", children: "No g-force samples on this lap." })) })] }), _jsx(Panel, { title: "Laps", children: _jsx(DataTable, { testId: "laps-table", columns: lapColumns, rows: laps, rowKey: (l) => l.lap, rowClass: (l) => [l.is_best ? "best" : "", l.lap === focusLap ? "selected" : ""].join(" "), onRowClick: (l) => setFocusLap(l.lap), maxHeight: 360 }) })] }));
}
