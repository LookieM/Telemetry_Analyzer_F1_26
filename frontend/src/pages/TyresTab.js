import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from "react";
import { useAllocation, useClearAllocation, useCompoundModel, useInventory, useLapChannels, useSaveAllocation, useSaveTargets, useTyres, } from "../api/hooks";
import { CarGrid } from "../components/CarGrid";
import { StintTimeline } from "../components/StintTimeline";
import { TraceChart } from "../components/TraceChart";
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel, RecordTable } from "../components/ui";
import { fmt, fmtSigned } from "../lib/format";
import { stintSegments, stintTrace, tyreLapColumns, tyreLapTrace } from "../lib/traces";
function useDebounced(value, ms) {
    const [v, setV] = useState(value);
    useEffect(() => {
        const t = setTimeout(() => setV(value), ms);
        return () => clearTimeout(t);
    }, [value, ms]);
    return v;
}
function stintColumns(limit) {
    const mean = (s, ws) => {
        const vals = ws.map((w) => s.temp_mean[w]).filter((v) => v != null);
        return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    };
    return [
        { key: "n", header: "Stint", align: "right", render: (s) => s.stint.idx + 1 },
        { key: "comp", header: "Compound", render: (s) => _jsxs(_Fragment, { children: [_jsx("span", { className: "chip", style: { background: s.color } }), s.label] }) },
        { key: "laps", header: "Laps", render: (s) => `${s.stint.laps[0]}–${s.stint.laps[s.stint.laps.length - 1]} (${s.stint.laps.length})` },
        { key: "push", header: "Push laps", align: "right", render: (s) => s.stint.push_laps.length },
        { key: "deg", header: "Deg (s/lap)", align: "right", render: (s) => fmtSigned(s.deg.slope, 3) },
        { key: "r2", header: "R²", align: "right", render: (s) => fmt(s.deg.r2, 2) },
        { key: "cliff", header: "Cliff at age", align: "right", render: (s) => (s.deg.cliff_age != null ? String(s.deg.cliff_age) : "—") },
        { key: "lim", header: "Limiting", render: (s) => s.limiting_wheel ?? "—" },
        { key: "wr", header: "Wear (%/lap)", align: "right", render: (s) => fmt(s.limiting_wheel ? s.wear_rate[s.limiting_wheel] : null, 2) },
        { key: "wn", header: "Max wear (%)", align: "right", render: (s) => fmt(s.wear_now, 1) },
        { key: "ll", header: `Laps to ${limit.toFixed(0)}%`, align: "right", render: (s) => fmt(s.laps_to_limit, 1) },
        { key: "wu", header: "Warm-up (s)", align: "right", render: (s) => fmt(s.warmup_s, 2) },
        { key: "fuel", header: "Fuel (kg/lap)", align: "right", render: (s) => fmt(s.fuel_per_lap, 2) },
        {
            key: "t",
            header: "T front / rear (°C)",
            align: "right",
            render: (s) => {
                const f = mean(s, ["FL", "FR"]);
                const r = mean(s, ["RL", "RR"]);
                return f != null && r != null ? `${f.toFixed(0)} / ${r.toFixed(0)}` : "—";
            },
        },
    ];
}
function PressurePanel({ stint, kind }) {
    const save = useSaveTargets();
    const t = stint.targets;
    const measured = (ws) => {
        const v = ws.map((w) => stint.hot_psi[w]).filter((x) => x != null);
        return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
    };
    const [lo, setLo] = useState(t.temp_lo);
    const [hi, setHi] = useState(t.temp_hi);
    const r1 = (v) => Math.round(v * 10) / 10;
    const [front, setFront] = useState(r1(t.hot_front_psi ?? measured(["FL", "FR"]) ?? 22));
    const [rear, setRear] = useState(r1(t.hot_rear_psi ?? measured(["RL", "RR"]) ?? 22));
    useEffect(() => {
        setLo(t.temp_lo);
        setHi(t.temp_hi);
        setFront(r1(t.hot_front_psi ?? measured(["FL", "FR"]) ?? 22));
        setRear(r1(t.hot_rear_psi ?? measured(["RL", "RR"]) ?? 22));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [stint.stint.idx, stint.stint.compound, t.temp_lo, t.temp_hi, t.hot_front_psi, t.hot_rear_psi]);
    const code = stint.stint.compound;
    const num = (set) => (e) => set(Number(e.target.value));
    return (_jsxs(Panel, { title: `Pressures & window — ${stint.label} (stint ${stint.stint.idx + 1}, push laps only)`, testId: "pressure-panel", children: [_jsxs("div", { className: "row", children: [_jsxs("label", { className: "field", children: ["Window low (\u00B0C)", _jsx("input", { type: "number", step: 1, value: lo, onChange: num(setLo) })] }), _jsxs("label", { className: "field", children: ["Window high (\u00B0C)", _jsx("input", { type: "number", step: 1, value: hi, onChange: num(setHi) })] }), _jsxs("label", { className: "field", children: ["Hot target front (psi)", _jsx("input", { type: "number", step: 0.1, value: front, onChange: num(setFront) })] }), _jsxs("label", { className: "field", children: ["Hot target rear (psi)", _jsx("input", { type: "number", step: 0.1, value: rear, onChange: num(setRear) })] }), _jsx("button", { disabled: code == null || save.isPending, onClick: () => code != null && save.mutate({ code, kind, temp_lo: lo, temp_hi: hi, hot_front_psi: front, hot_rear_psi: rear }), children: "Save targets" })] }), save.isError && _jsx(ErrorBox, { error: save.error }), save.isSuccess && _jsxs("p", { className: "note", children: ["Saved targets for ", stint.label, "."] }), _jsx("div", { style: { marginTop: 8 }, children: _jsx(RecordTable, { rows: stint.pressure, testId: "pressure-table", formats: Object.fromEntries(Object.keys(stint.pressure[0] ?? {}).map((k) => [k, (v) => (/Change|Build/.test(k) ? fmtSigned(v, 1) : v.toFixed(1))])) }) }), _jsx("p", { className: "note", children: "Cold set needed = cold set now + (hot target \u2212 hot measured). The game's build-up is small (~0\u20131 psi)." })] }));
}
function ModelPanel({ track, state, wearLimit }) {
    const model = useCompoundModel(track, state, wearLimit);
    const alloc = useAllocation(track);
    const saveAlloc = useSaveAllocation();
    const clearAlloc = useClearAllocation();
    const [pick, setPick] = useState({ soft: null, medium: null, hard: null });
    useEffect(() => {
        if (alloc.data)
            setPick({ soft: alloc.data.soft, medium: alloc.data.medium, hard: alloc.data.hard });
    }, [alloc.data]);
    const comps = Object.values(model.data?.compounds ?? {}).sort((a, b) => a.code - b.code);
    const columns = [
        { key: "c", header: "Compound", render: (m) => _jsxs(_Fragment, { children: [_jsx("span", { className: "chip", style: { background: m.color } }), m.label] }) },
        { key: "o", header: "Offset vs ref (s)", align: "right", render: (m) => fmt(m.offset_s, 3) },
        { key: "d", header: "Deg (s/lap)", align: "right", render: (m) => fmt(m.deg_s_per_lap, 3) },
        { key: "w", header: "Wear (%/lap)", align: "right", render: (m) => fmt(m.wear_pct_per_lap, 2) },
        { key: "m", header: `Max laps @ ${wearLimit.toFixed(0)}%`, align: "right", render: (m) => m.max_laps ?? "—" },
        { key: "u", header: "Warm-up (s)", align: "right", render: (m) => fmt(m.warmup_s, 2) },
        { key: "s", header: "Stints / laps", align: "right", render: (m) => `${m.n_stints} / ${m.n_laps}` },
        { key: "src", header: "Source", render: (m) => m.source },
        { key: "n", header: "Note", render: (m) => _jsx("span", { className: "dim", children: m.note }) },
    ];
    const options = alloc.data?.options ?? [];
    const picker = (role, label) => (_jsxs("label", { className: "field", children: [label, _jsxs("select", { value: pick[role] ?? "", onChange: (e) => setPick({ ...pick, [role]: e.target.value === "" ? null : Number(e.target.value) }), "aria-label": `${label} compound`, children: [_jsx("option", { value: "", children: "\u2014" }), options.map((o) => (_jsx("option", { value: o.code, children: o.label }, o.code)))] })] }, role));
    return (_jsxs(Panel, { title: `Compound model — ${track} (all library sessions)`, testId: "model-panel", children: [model.isLoading && _jsx(Loading, { what: "Building the compound model\u2026" }), model.isError && _jsx(ErrorBox, { error: model.error }), model.data && comps.length === 0 && _jsx("p", { className: "note", children: "Not enough long runs on this track yet (need \u22654 push laps on one set)." }), comps.length > 0 && model.data && (_jsxs(_Fragment, { children: [_jsx(DataTable, { columns: columns, rows: comps, rowKey: (m) => m.code, testId: "model-table" }), _jsxs("p", { className: "note", children: ["Base pace ", fmt(model.data.base_pace_s, 3), " s (new tyre, 5 kg) \u00B7 pit loss", " ", model.data.pit_loss ? `${model.data.pit_loss.toFixed(1)} s from ${model.data.pit_losses.length} stop(s)` : "not measured yet", " \u00B7 sessions used:", " ", model.data.sources.map((i) => `#${i}`).join(", ") || "—", "."] })] })), _jsxs("div", { className: "row", style: { marginTop: 10 }, children: [picker("soft", "S"), picker("medium", "M"), picker("hard", "H"), _jsx("button", { disabled: saveAlloc.isPending, onClick: () => saveAlloc.mutate({ track, ...pick }), children: "Save S/M/H" }), _jsx("button", { disabled: clearAlloc.isPending, onClick: () => clearAlloc.mutate(track), children: "Use inferred" }), _jsxs("span", { className: "note", children: ["S/M/H for ", track, ": ", alloc.data?.source ?? "…"] })] })] }));
}
function Body({ detail, tyres, focusLap, setFocusLap, limitInput, setLimitInput }) {
    const sessionId = detail.session.id;
    const summaries = tyres.stints;
    const focusStint = summaries.find((s) => focusLap != null && s.stint.laps.includes(focusLap)) ?? summaries[0];
    const inv = useInventory(sessionId);
    const cols = useMemo(() => tyreLapColumns(inv.data), [inv.data]);
    const channels = useLapChannels(sessionId, focusLap, cols.all, !!inv.data && cols.all.length > 1);
    const traceData = useMemo(() => {
        if (!channels.data || !focusStint)
            return null;
        return tyreLapTrace(channels.data, cols, { lo: focusStint.targets.temp_lo, hi: focusStint.targets.temp_hi });
    }, [channels.data, cols, focusStint]);
    const stintData = useMemo(() => stintTrace(tyres), [tyres]);
    const limit = tyres.wear_limit;
    const columns = useMemo(() => stintColumns(limit), [limit]);
    const row = tyres.wheel_table.find((r) => r.lap === focusLap);
    const lapsTotal = Math.max(1, ...tyres.wheel_table.map((r) => r.lap)) + 1;
    const lim = focusStint?.limiting_wheel ?? null;
    if (!focusStint)
        return _jsx("p", { className: "note", children: "No tyre stints found in this session." });
    return (_jsxs(_Fragment, { children: [_jsxs(MetricRow, { children: [_jsx(Metric, { label: "Compound", value: focusStint.label, testId: "metric-compound" }), _jsx(Metric, { label: "Tyre age", value: `${focusLap != null ? (focusStint.stint.ages[String(focusLap)] ?? 0) : 0} laps`, sub: "laps on this set before the focus lap" }), _jsx(Metric, { label: "Degradation", value: `${fmtSigned(focusStint.deg.slope, 3)} s/lap`, sub: `fuel-corrected, push laps · R² ${fmt(focusStint.deg.r2, 2)}` }), _jsx(Metric, { label: `Wear (${lim ?? "—"})`, value: `${fmt(lim ? focusStint.wear_rate[lim] : null, 2)} %/lap` }), _jsx(Metric, { label: `Laps to ${limit.toFixed(0)}%`, value: fmt(focusStint.laps_to_limit, 1) }), _jsx("div", { className: "metric", children: _jsxs("label", { className: "field", children: ["Wear limit (%)", _jsx("input", { type: "number", min: 30, max: 95, step: 1, value: limitInput, onChange: (e) => setLimitInput(e.target.value), "aria-label": "Wear limit" })] }) })] }), _jsxs(Panel, { title: "Stints", children: [_jsx(StintTimeline, { rows: [{ label: "This session", stints: stintSegments(summaries) }], lapsTotal: lapsTotal }), _jsxs("label", { className: "field toolbar-row", style: { marginTop: 10, maxWidth: 260 }, children: ["Focus lap", _jsx("select", { value: focusLap ?? "", onChange: (e) => setFocusLap(Number(e.target.value)), "aria-label": "Focus lap", children: detail.laps.map((l) => (_jsxs("option", { value: l.lap, children: ["Lap ", l.lap, " \u2014 ", l.lap_class] }, l.lap))) })] })] }), _jsxs("div", { className: "grid-2-wide", children: [_jsxs(Panel, { title: "Tyres over the lap", children: [channels.isLoading && _jsx(Loading, { what: "Loading channels\u2026" }), channels.isError && _jsx(ErrorBox, { error: channels.error }), traceData && _jsx(TraceChart, { data: traceData, sync: "lap", testId: "tyre-lap-trace" })] }), _jsxs(Panel, { title: `Lap ${focusLap ?? "?"} · ${row?.lap_class ?? ""} lap`, children: [row && _jsx(CarGrid, { row: row, targets: focusStint.targets, wearRate: focusStint.wear_rate }), tyres.temp_channel && _jsxs("p", { className: "note", children: ["Temperature channel: ", tyres.temp_channel, "."] })] })] }), _jsx(Panel, { title: "Stints table", children: _jsx(DataTable, { testId: "stints-table", columns: columns, rows: summaries, rowKey: (s) => s.stint.idx }) }), _jsxs(Panel, { title: "Stint trends", children: [_jsx(TraceChart, { data: stintData, sync: "stint", testId: "stint-trace" }), _jsxs("p", { className: "note", children: ["Lap times corrected to 5 kg with ", tyres.race_stats.fuel_s_per_kg.toFixed(3), " s/kg (fuel + track evolution,", " ", tyres.race_stats.fuel_pairs ? `measured from ${tyres.race_stats.fuel_pairs} same-compound stint pairs in your races` : "default", "). Hollow points = start / in / pit / out / SC / slow laps, left out of the trends. Drag to zoom, double-click to reset."] })] }), _jsx(PressurePanel, { stint: focusStint, kind: tyres.temp_kind }), _jsx(ModelPanel, { track: tyres.track, state: tyres.state, wearLimit: limit })] }));
}
export function TyresTab({ detail, focusLap, setFocusLap }) {
    const [limitInput, setLimitInput] = useState("");
    const debounced = useDebounced(limitInput, 500);
    const wearLimit = debounced !== "" && Number.isFinite(Number(debounced)) && Number(debounced) >= 1 && Number(debounced) <= 100 ? Number(debounced) : null;
    const tyres = useTyres(detail.session.id, wearLimit);
    useEffect(() => {
        if (limitInput === "" && tyres.data)
            setLimitInput(String(tyres.data.wear_limit));
    }, [tyres.data, limitInput]);
    return (_jsxs("div", { className: "stack", "data-testid": "tyres-tab", children: [tyres.isLoading && _jsx(Loading, { what: "Analysing tyres\u2026" }), tyres.isError && _jsx(ErrorBox, { error: tyres.error }), tyres.data && _jsx(Body, { detail: detail, tyres: tyres.data, focusLap: focusLap, setFocusLap: setFocusLap, limitInput: limitInput, setLimitInput: setLimitInput })] }));
}
