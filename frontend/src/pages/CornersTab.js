import { jsxs as _jsxs, jsx as _jsx, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../api/client";
import { useBalance, useCompare, useCorners, useMap, useRebuildCorners } from "../api/hooks";
import { BalanceStrip } from "../components/BalanceStrip";
import { LapSelect, ReferenceFields, useReference } from "../components/ReferencePicker";
import { TraceChart } from "../components/TraceChart";
import { TrackMap } from "../components/TrackMap";
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel } from "../components/ui";
import { balanceUnavailable, buildBalanceColumns } from "../lib/balance";
import { biggestLoss, buildCornerRows, cornerAt, cornerMarkers, lossKind, sortRows, zoomRange } from "../lib/corners";
import { selectGroup, useCursorStore } from "../lib/cursor";
import { fmt, fmtSigned } from "../lib/format";
import { fastestOtherLap } from "../lib/sessions";
import { compareTrace, cornerBands } from "../lib/traces";
import "./CornersTab.css";
const SYNC = "corners";
const SPEED_STEP_KMH = 3;
function SortHeader({ label, k, sort, onSort }) {
    const active = sort.key === k;
    return (_jsxs("button", { className: `ct-sort${active ? " active" : ""}`, onClick: () => onSort(k), title: "Sort by this column", children: [label, active ? (sort.dir === "asc" ? " ▲" : " ▼") : ""] }));
}
/** A value with its difference to the reference; speed differences are coloured (higher is better). */
function Value({ v, d, decimals = 0, speed = false, unit = "" }) {
    const tone = speed && d != null && Math.abs(d) >= SPEED_STEP_KMH ? (d > 0 ? "good" : "bad") : "";
    return (_jsxs(_Fragment, { children: [fmt(v, decimals), unit, d != null && _jsx("span", { className: `ct-delta ${tone}`, children: fmtSigned(d, decimals) })] }));
}
export function CornersTab({ detail, focusLap, setFocusLap }) {
    const { session, laps } = detail;
    const choice = useReference(detail, "lap");
    const { selection } = choice;
    const resetCursor = useCursorStore((s) => s.reset);
    const cursor = useCursorStore(selectGroup(SYNC));
    const [sort, setSort] = useState({ key: "order", dir: "asc" });
    const [selectedId, setSelectedId] = useState(null);
    const [balanceView, setBalanceView] = useState("lap");
    useEffect(() => {
        resetCursor(SYNC);
        setSelectedId(null);
        return () => resetCursor(SYNC);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [session.id]);
    // The same lap as focus and reference shows only zeros: start from the fastest other clean lap instead.
    useEffect(() => {
        if (choice.mode === "lap" && choice.refLap != null && choice.refLap === focusLap) {
            const other = fastestOtherLap(laps, focusLap);
            if (other != null)
                choice.setRefLap(other);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [session.id, focusLap, choice.mode, choice.refLap]);
    const refLap = selection?.lap ?? null;
    const refSession = selection?.session ?? null;
    const corners = useCorners(session.id, focusLap, refLap, refSession, !!selection);
    const cmp = useCompare(session.id, focusLap, refLap, refSession, !!selection);
    const map = useMap(session.id, focusLap, refLap, refSession, "speed");
    const rebuild = useRebuildCorners();
    const sessionBalance = useBalance(session.id, balanceView === "session");
    const rows = useMemo(() => (corners.data ? buildCornerRows(corners.data) : []), [corners.data]);
    const shown = useMemo(() => sortRows(rows, sort.key, sort.dir), [rows, sort]);
    const selected = rows.find((r) => r.id === selectedId) ?? null;
    const worst = useMemo(() => biggestLoss(rows), [rows]);
    const trackLength = map.data?.track_length ?? null;
    const zoom = selected ? zoomRange(selected, trackLength) : null;
    const labels = useMemo(() => ({ cmp: `L${focusLap}`, ref: selection ? (selection.session ? `S${selection.session} L${selection.lap}` : `L${selection.lap}`) : "Ref" }), [focusLap, selection]);
    const bands = useMemo(() => cornerBands(rows.map((r) => ({ from: r.startM, to: r.endM, name: r.name }))), [rows]);
    const traceData = useMemo(() => {
        if (!cmp.data)
            return null;
        return { ...compareTrace(cmp.data, labels, 115), bands, markers: selected ? cornerMarkers(selected) : [] };
    }, [cmp.data, labels, bands, selected]);
    const marks = useMemo(() => (selected ? cornerMarkers(selected).map((m) => ({ d: m.x, label: m.label ?? "", color: m.color ?? "#888" })) : []), [selected]);
    const onSort = (key) => setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "order" ? "asc" : key === "timeDelta" ? "desc" : "asc" }));
    const select = (row) => setSelectedId((cur) => (cur === row.id ? null : row.id));
    const head = (label, k) => _jsx(SortHeader, { label: label, k: k, sort: sort, onSort: onSort });
    const columns = [
        { key: "order", header: head("#", "order"), align: "right", render: (r) => r.order },
        {
            key: "name",
            header: "Corner",
            render: (r) => (_jsxs("span", { className: "ct-name", title: `${fmt(r.startM, 0)}–${fmt(r.endM, 0)} m${r.complex ? " · complex of several minima" : ""}`, children: [r.name, _jsx("span", { className: "tag ct-class", children: r.speedClass })] })),
        },
        { key: "time", header: head("Time (s)", "time"), align: "right", render: (r) => fmt(r.time, 3) },
        {
            key: "timeDelta",
            header: head("Δ time (s)", "timeDelta"),
            align: "right",
            title: "Time in the corner minus the reference; corner deltas plus the straights add up to the lap delta",
            render: (r) => _jsx("span", { className: `ct-${lossKind(r.timeDelta)}`, children: fmtSigned(r.timeDelta, 3) }),
        },
        { key: "entry", header: head("Entry km/h", "entry"), align: "right", render: (r) => _jsx(Value, { v: r.entry, d: r.entryDelta, speed: true }) },
        { key: "vmin", header: head("Min km/h", "vmin"), align: "right", render: (r) => _jsx(Value, { v: r.vmin, d: r.vminDelta, speed: true }) },
        { key: "exit", header: head("Exit km/h", "exit"), align: "right", render: (r) => _jsx(Value, { v: r.exit, d: r.exitDelta, speed: true }) },
        { key: "brake", header: head("Brake at (m)", "brake"), align: "right", title: "Negative difference = braking earlier than the reference", render: (r) => _jsx(Value, { v: r.brake, d: r.brakeDelta }) },
        { key: "trail", header: head("Trail brake (m)", "trail"), align: "right", render: (r) => _jsx(Value, { v: r.trail, d: r.trailDelta }) },
        { key: "throttle", header: head("Full throttle at (m)", "throttle"), align: "right", title: "Positive difference = later on the throttle", render: (r) => _jsx(Value, { v: r.throttle, d: r.throttleDelta }) },
    ];
    const callouts = useMemo(() => [...rows].filter((r) => r.callouts.length).sort((a, b) => Math.abs(b.timeDelta ?? 0) - Math.abs(a.timeDelta ?? 0)), [rows]);
    const cursorX = cursor.hoverX ?? cursor.pinnedX;
    const cornerHere = cornerAt(rows, cursorX);
    const data = corners.data;
    const balanceBase = data?.balance_baseline;
    const shownBalance = balanceView === "session" ? sessionBalance.data : data;
    const balanceColumns = useMemo(() => {
        if (!data || !balanceBase)
            return [];
        if (balanceView === "session")
            return sessionBalance.data ? buildBalanceColumns(sessionBalance.data.corners.map((c) => ({ id: c.id, name: c.name, balance: c })), balanceBase) : [];
        return buildBalanceColumns(data.corners, balanceBase);
    }, [data, balanceBase, balanceView, sessionBalance.data]);
    const noData = corners.error instanceof ApiError && (corners.error.status === 404 || corners.error.status === 422);
    return (_jsxs("div", { className: "stack", "data-testid": "corners-tab", children: [_jsxs(Panel, { title: "Where and why do I lose time?", actions: data && focusLap != null ? (_jsxs("button", { disabled: rebuild.isPending, title: "Detect this track's corners again from the focus lap", onClick: () => {
                        if (window.confirm(`Rebuild the corners of ${session.track} from lap ${focusLap}? Every session of the track will use them.`))
                            rebuild.mutate({ track: data.track, session: session.id, lap: focusLap });
                    }, children: ["Rebuild corners from lap ", focusLap] })) : undefined, children: [_jsxs("div", { className: "row toolbar-row", children: [_jsx(LapSelect, { laps: laps, value: focusLap, onChange: setFocusLap, label: "Focus lap" }), _jsx(ReferenceFields, { choice: choice, modes: ["lap", "session"] })] }), data && (_jsxs("p", { className: "note", children: ["Corners detected from ", data.corners_source.session === session.id ? "this session's" : `session #${data.corners_source.session}'s`, " lap ", data.corners_source.lap, ". Time in a corner is measured from the aligned delta, positive = slower than the reference."] })), data && data.lap === data.reference.lap && data.reference.session === session.id && (_jsx("p", { className: "note", "data-testid": "corners-same-lap", children: "Focus and reference are the same lap, so every difference is zero. Pick another focus or reference lap." })), rebuild.isError && _jsx(ErrorBox, { error: rebuild.error })] }), !selection && _jsx("p", { className: "note", children: "Pick a reference lap to compare against." }), corners.isLoading && _jsx(Loading, { what: "Detecting corners and comparing laps\u2026" }), corners.isError && (noData ? _jsxs("p", { className: "note", "data-testid": "corners-nodata", children: ["Not enough data for corners: ", corners.error.message] }) : _jsx(ErrorBox, { error: corners.error })), data && (_jsxs(_Fragment, { children: [_jsxs(MetricRow, { children: [_jsx(Metric, { label: "Lap \u0394 vs reference", value: _jsxs("span", { className: data.lap_delta > 0 ? "bad" : "good", children: [fmtSigned(data.lap_delta, 3), " s"] }), sub: data.lap_delta > 0 ? "slower" : "faster", testId: "metric-lap-delta" }), _jsx(Metric, { label: "In corners", value: _jsxs("span", { className: data.sum_corner_delta > 0 ? "bad" : "good", children: [fmtSigned(data.sum_corner_delta, 3), " s"] }), sub: `${rows.length} corners`, testId: "metric-corner-sum" }), _jsx(Metric, { label: "On straights", value: _jsxs("span", { className: data.straights_delta > 0 ? "bad" : "good", children: [fmtSigned(data.straights_delta, 3), " s"] }), sub: "between the corners", testId: "metric-straights" }), _jsx(Metric, { label: "Biggest loss", value: worst ? worst.name : "—", sub: worst ? `${fmtSigned(worst.timeDelta, 3)} s` : "nothing above the noise", testId: "metric-worst" }), _jsx(Metric, { label: "At cursor", value: cursorX != null ? `${cursorX.toFixed(0)} m` : "—", sub: cornerHere ?? "" })] }), _jsxs(Panel, { title: `${data.track} corners — lap ${data.lap} vs ${data.reference.session !== session.id ? `#${data.reference.session} ` : ""}lap ${data.reference.lap}`, children: [_jsx(DataTable, { testId: "corner-table", columns: columns, rows: shown, rowKey: (r) => r.id, rowClass: (r) => (r.id === selectedId ? "selected ct-selected" : undefined), onRowClick: select, maxHeight: 440 }), _jsx("p", { className: "note", children: "Click a corner to zoom the map and traces to it \u00B7 click again to show the whole lap \u00B7 click a column title to sort." })] }), _jsxs("div", { className: "grid-2", children: [_jsxs(Panel, { title: selected ? `${selected.name} (${selected.speedClass}) · ${fmt(selected.startM, 0)}–${fmt(selected.endM, 0)} m` : `${data.track} — lap ${data.lap}`, actions: selected ? _jsx("button", { onClick: () => setSelectedId(null), children: "Whole lap" }) : undefined, children: [map.isLoading && _jsx(Loading, { what: "Loading map\u2026" }), map.isError && _jsx(ErrorBox, { error: map.error }), map.data && _jsx(TrackMap, { data: map.data, sync: SYNC, height: 520, zoom: zoom, marks: marks })] }), _jsxs(Panel, { title: "Driver trace", children: [cmp.isLoading && _jsx(Loading, { what: "Loading channels\u2026" }), cmp.isError && _jsx(ErrorBox, { error: cmp.error }), traceData && _jsx(TraceChart, { data: traceData, sync: SYNC, testId: "corner-trace", zoom: zoom }), _jsx("p", { className: "note", children: "Drag on a trace to zoom \u00B7 double-click to reset \u00B7 click to pin the cursor. Dashed lines mark the brake and full-throttle points of the selected corner." })] })] }), _jsxs(Panel, { title: "Balance, traction and lock-ups", testId: "balance-panel", actions: _jsxs("div", { className: "bal-modes", children: [_jsxs("button", { className: balanceView === "lap" ? "active" : "", onClick: () => setBalanceView("lap"), title: "Balance of the focus lap", children: ["Lap ", focusLap] }), _jsx("button", { className: balanceView === "session" ? "active" : "", onClick: () => setBalanceView("session"), title: "Median over the session's clean laps, so one mistake does not decide", children: "Session median" })] }), children: [balanceView === "session" && sessionBalance.isLoading && _jsx(Loading, { what: "Measuring balance over the clean laps\u2026" }), balanceView === "session" && sessionBalance.isError && _jsx(ErrorBox, { error: sessionBalance.error }), shownBalance && balanceUnavailable(shownBalance) ? (_jsxs("p", { className: "note", "data-testid": "balance-nodata", children: ["Not enough data for balance: ", balanceUnavailable(shownBalance)] })) : (shownBalance && (_jsxs(_Fragment, { children: [_jsx("p", { className: "bal-summary", "data-testid": "balance-summary", children: shownBalance.balance_summary ?? "—" }), _jsx("p", { className: "note", children: balanceView === "session" && sessionBalance.data ? `Median over ${sessionBalance.data.laps} clean laps (${sessionBalance.data.lap_numbers.join(", ")}).` : `Focus lap ${data.lap}.` }), _jsx(BalanceStrip, { columns: balanceColumns, selectedId: selectedId, onSelect: (id) => setSelectedId((cur) => (cur === id ? null : id)), lockups: shownBalance.lockups })] })))] }), _jsx(Panel, { title: "What changed", children: callouts.length === 0 ? (_jsxs("p", { className: "note", "data-testid": "corner-callouts-empty", children: ["No corner differs from the reference by more than the noise (", "±", "0.03 s)."] })) : (_jsx("ul", { className: "ct-callouts", "data-testid": "corner-callouts", children: callouts.map((r) => (_jsx("li", { className: lossKind(r.timeDelta) === "flat" ? "" : lossKind(r.timeDelta), onClick: () => select(r), children: r.callouts[0] }, r.id))) })) })] }))] }));
}
