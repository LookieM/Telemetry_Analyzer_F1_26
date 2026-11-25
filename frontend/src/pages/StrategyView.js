import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/** Strategy model + optimiser view, shared by the Session > Strategy tab and the Planner. */
import { useEffect, useMemo, useState } from "react";
import { useClearOverrides, useOptimise, useSaveOverrides } from "../api/hooks";
import { StintTimeline } from "../components/StintTimeline";
import { TraceChart } from "../components/TraceChart";
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel, RecordTable } from "../components/ui";
import { TRACK_STATES, TYRE_STATE_LABEL } from "../lib/constants";
import { fmt, formatRaceTime, fmtSigned, windowsText } from "../lib/format";
import { raceTrace } from "../lib/traces";
import { TyreSetsPanel } from "./TyreSetsPanel";
function useDebounced(value, ms) {
    const [v, setV] = useState(value);
    useEffect(() => {
        const t = setTimeout(() => setV(value), ms);
        return () => clearTimeout(t);
    }, [value, ms]);
    return v;
}
/** Stint segments of one plan for the timeline. */
function planSegments(plan, data) {
    let lap = 1;
    return plan.compounds.map((code, i) => {
        const n = plan.stints[i];
        const wear = plan.start_wear?.[i] ?? 0;
        const entry = data.allocation[String(code)];
        const spec = data.specs.find((s) => s.code === code);
        const role = entry?.role ?? null;
        const seg = {
            from: lap,
            to: lap + n - 1,
            color: spec?.color ?? entry?.color ?? "#8A9099",
            text: role || spec?.label || String(code),
            title: `${spec?.label ?? code}${wear >= 0.5 ? ` (used ${Math.round(wear)}%)` : ""} · L${lap}–${lap + n - 1}`,
            light: role === "H",
        };
        lap += n;
        return seg;
    });
}
function NumberField({ label, value, onChange, step, min, max, title }) {
    return (_jsxs("label", { className: "field", title: title, children: [label, _jsx("input", { type: "number", step: step, min: min, max: max, value: Number.isFinite(value) ? Number(value.toFixed(4)) : "", onChange: (e) => e.target.value !== "" && onChange(Number(e.target.value)), "aria-label": label })] }));
}
export function StrategyView({ track, state, onStateChange, review, testId }) {
    const [paramEdits, setParamEdits] = useState({});
    const [specEdits, setSpecEdits] = useState({});
    const [panel, setPanel] = useState(review ? "review" : "sensitivity");
    const [useInventory, setUseInventory] = useState(true);
    const save = useSaveOverrides();
    const clear = useClearOverrides();
    useEffect(() => {
        setParamEdits({});
        setSpecEdits({});
    }, [track, state]);
    const request = useMemo(() => ({
        track,
        state,
        params: paramEdits,
        specs: Object.entries(specEdits).map(([code, e]) => ({ code: Number(code), ...e })),
        use_inventory: useInventory,
    }), [track, state, paramEdits, specEdits, useInventory]);
    const debounced = useDebounced(request, 350);
    const opt = useOptimise(debounced);
    const data = opt.data;
    const setParam = (key, value) => setParamEdits((p) => ({ ...p, [key]: value }));
    const setSpec = (code, edit) => setSpecEdits((s) => ({ ...s, [code]: { ...s[code], ...edit } }));
    const rows = useMemo(() => {
        if (!data?.best)
            return [];
        const best = data.best;
        const out = data.plans.slice(0, 5).map((p, i) => ({
            label: `#${i + 1} ${p.stops}-stop`,
            stints: planSegments(p, data),
            note: Math.abs((p.delta_best ?? 0)) < 1e-6 ? "best" : `${fmtSigned(p.delta_best, 1)} s`,
        }));
        if (review?.review) {
            const r = review.review;
            out.push({ label: "Actual (this race)", stints: planSegments(r.actual, data), note: `${fmtSigned(r.model_actual_time - best.race_time, 1)} s` });
        }
        return out;
    }, [data, review]);
    const trace = useMemo(() => (data ? raceTrace(data, review?.review ?? null) : null), [data, review]);
    const specColumns = data
        ? [
            {
                key: "use",
                header: "Use",
                render: (s) => _jsx("input", { type: "checkbox", checked: specEdits[s.code]?.use ?? s.use, onChange: (e) => setSpec(s.code, { use: e.target.checked }), "aria-label": `Use ${s.label}` }),
            },
            { key: "c", header: "Compound", render: (s) => _jsxs(_Fragment, { children: [_jsx("span", { className: "chip", style: { background: s.color } }), s.label] }) },
            { key: "o", header: "Offset (s)", title: "Pace vs the reference compound at the same tyre age and fuel (negative = faster).", render: (s) => _jsx(SpecInput, { value: s.offset_s, step: 0.01, label: `${s.label} offset`, onChange: (v) => setSpec(s.code, { offset_s: v }) }) },
            { key: "d", header: "Deg (s/lap)", title: "Time lost per lap of tyre age (fuel-corrected).", render: (s) => _jsx(SpecInput, { value: s.deg_s_per_lap, step: 0.005, min: 0, label: `${s.label} deg`, onChange: (v) => setSpec(s.code, { deg_s_per_lap: v }) }) },
            { key: "w", header: "Wear (%/lap)", title: "Limiting-wheel wear rate; caps the stint at the wear limit.", render: (s) => _jsx(SpecInput, { value: s.wear_pct_per_lap ?? 0, step: 0.1, min: 0, label: `${s.label} wear`, onChange: (v) => setSpec(s.code, { wear_pct_per_lap: v }) }) },
            { key: "u", header: "Warm-up (s)", render: (s) => _jsx(SpecInput, { value: s.warmup_s, step: 0.05, label: `${s.label} warm-up`, onChange: (v) => setSpec(s.code, { warmup_s: v }) }) },
            { key: "s", header: "Source", render: (s) => (specEdits[s.code] && Object.keys(specEdits[s.code]).some((k) => k !== "use") ? "manual" : s.source) },
            { key: "n", header: "Note", render: (s) => _jsx("span", { className: "dim", children: data.notes[String(s.code)] ?? "" }) },
        ]
        : [];
    const p = data?.params;
    const fuelNote = p ? `${p.fuel_per_lap_kg.toFixed(2)} kg/lap + ${p.fuel_margin_laps} lap` : "";
    const reviewObj = review?.review ?? null;
    return (_jsxs("div", { className: "stack", "data-testid": testId ?? "strategy-view", children: [_jsx(Panel, { className: "toolbar", children: _jsxs("div", { className: "row", children: [_jsx("strong", { className: "sv-track", children: data?.track ?? track }), onStateChange ? (_jsxs("label", { className: "field", children: ["Track state", _jsx("select", { value: state, onChange: (e) => onStateChange(e.target.value), "aria-label": "Track state", children: TRACK_STATES.map((s) => (_jsx("option", { value: s, children: TYRE_STATE_LABEL[s] }, s))) })] })) : (_jsx("span", { className: "dim", children: state })), data && (_jsxs("span", { className: "note", "data-testid": "model-sources", children: ["model from ", data.sources.length ? `sessions ${data.sources.map((i) => `#${i}`).join(", ")}` : "no long runs yet — manual model", " \u00B7", " ", data.model.pit_loss ? `pit loss measured ${data.model.pit_loss.toFixed(1)} s` : "pit loss from track fallback", data.saved_overrides ? " · saved overrides applied" : ""] }))] }) }), opt.isLoading && _jsx(Loading, { what: "Building the compound model from your library\u2026" }), opt.isError && _jsx(ErrorBox, { error: opt.error }), data && p && (_jsxs(_Fragment, { children: [_jsx(Panel, { title: "Race parameters", children: _jsxs("div", { className: "row", children: [_jsx(NumberField, { label: "Race laps", value: p.laps, step: 1, min: 1, max: 120, onChange: (v) => setParam("laps", Math.round(v)) }), _jsx(NumberField, { label: "Pit loss (s)", value: p.pit_loss_s, step: 0.5, min: 0, max: 60, onChange: (v) => setParam("pit_loss_s", v) }), _jsx(NumberField, { label: "Fuel burn (kg/lap)", value: p.fuel_per_lap_kg, step: 0.05, min: 0.1, max: 5, onChange: (v) => setParam("fuel_per_lap_kg", v) }), _jsx(NumberField, { label: "Fuel effect (s/kg)", value: p.fuel_effect_s_per_kg, step: 0.005, min: 0, max: 0.2, onChange: (v) => setParam("fuel_effect_s_per_kg", v) }), _jsx(NumberField, { label: "Wear limit (%)", value: p.wear_limit_pct, step: 1, min: 30, max: 95, onChange: (v) => setParam("wear_limit_pct", v) }), _jsx(NumberField, { label: "SC pit loss \u00D7", value: p.sc_pit_factor, step: 0.05, min: 0.1, max: 1, title: "Pit loss under safety car as a share of the green-flag loss.", onChange: (v) => setParam("sc_pit_factor", v) }), _jsx(NumberField, { label: "Base pace (s)", value: p.base_pace_s, step: 0.1, min: 30, max: 200, title: "Reference compound, new tyre, 5 kg fuel.", onChange: (v) => setParam("base_pace_s", v) }), _jsx(NumberField, { label: "Fuel margin (laps)", value: p.fuel_margin_laps, step: 0.5, min: 0, max: 5, onChange: (v) => setParam("fuel_margin_laps", v) }), _jsx(NumberField, { label: "Max stops", value: p.max_stops, step: 1, min: 0, max: 4, onChange: (v) => setParam("max_stops", Math.round(v)) }), _jsx(NumberField, { label: "Window tolerance (s)", value: p.window_tolerance_s, step: 0.5, min: 0.1, max: 10, onChange: (v) => setParam("window_tolerance_s", v) }), _jsxs("label", { className: "field", children: ["Two dry compounds", _jsx("input", { type: "checkbox", checked: p.require_two_compounds, onChange: (e) => setParam("require_two_compounds", e.target.checked), "aria-label": "Two dry compounds" })] })] }) }), _jsx(TyreSetsPanel, { track: data.track, inventory: data.inventory, specs: data.specs, useInventory: useInventory, onUseInventory: setUseInventory }), _jsxs(Panel, { title: "Compound model \u2014 edit any value; the plan updates immediately", actions: _jsxs(_Fragment, { children: [_jsx("button", { disabled: save.isPending, onClick: () => save.mutate({ ...request }), children: "Save as track defaults" }), _jsx("button", { disabled: clear.isPending, onClick: () => clear.mutate({ track, state }, {
                                        onSuccess: () => {
                                            setParamEdits({});
                                            setSpecEdits({});
                                        },
                                    }), children: "Reset to measured" })] }), children: [_jsx(DataTable, { columns: specColumns, rows: data.specs, rowKey: (s) => s.code, testId: "specs-table" }), (save.isSuccess || clear.isSuccess) && _jsx("p", { className: "note", children: clear.isSuccess && !save.isSuccess ? "Reset to measured." : "Saved for this track and track state." }), (save.isError || clear.isError) && _jsx(ErrorBox, { error: save.error ?? clear.error })] }), data.message || !data.best ? (_jsx("div", { className: "error-box", role: "alert", "data-testid": "no-plan", children: data.message ?? "No feasible plan." })) : (_jsxs(_Fragment, { children: [_jsxs(MetricRow, { children: [_jsx(Metric, { label: "Best plan", value: `${data.best.stops}-stop`, sub: data.best.label, testId: "best-plan" }), _jsx(Metric, { label: "Race time (model)", value: formatRaceTime(data.best.race_time) }), _jsx(Metric, { label: "Box", value: windowsText(data.best.stop_laps, data.best.windows), testId: "best-box" }), _jsx(Metric, { label: "Start fuel", value: `${p.start_fuel_kg.toFixed(1)} kg`, sub: fuelNote })] }), _jsxs(Panel, { title: "Ranked plans", children: [_jsx(PlansTable, { plans: data.plans }), _jsx("div", { style: { marginTop: 12 }, children: _jsx(StintTimeline, { rows: rows, lapsTotal: p.laps }) }), _jsx("p", { className: "note", children: "Stint order is free in this model (no fuel \u00D7 compound interaction) \u2014 the softest set is listed first." })] }), trace && (_jsx(Panel, { title: "Race trace", children: _jsx(TraceChart, { data: trace, sync: "race", testId: "race-trace" }) })), _jsxs(Panel, { title: _jsx("span", { className: "row", style: { gap: 4 }, children: (review ? ["review", "sensitivity", "calls"] : ["sensitivity", "calls"]).map((k) => (_jsx("button", { className: panel === k ? "primary" : "ghost", onClick: () => setPanel(k), "data-testid": `panel-${k}`, children: k === "review" ? "Race review" : k === "calls" ? "Pit-wall calls" : "Sensitivity" }, k))) }), children: [panel === "sensitivity" && (_jsxs(_Fragment, { children: [_jsx(RecordTable, { rows: data.sensitivity, testId: "sensitivity-table" }), _jsx("p", { className: "note", children: "'Baseline plan costs' = time lost if you keep the best plan above when the scenario is the real one." })] })), panel === "calls" && (_jsxs(_Fragment, { children: [_jsx(RecordTable, { rows: data.calls, testId: "calls-table", maxHeight: 360 }), _jsx("p", { className: "note", children: "Along the best plan. Negative = boxing now is faster than staying out (and boxing later at the normal loss). Undercut gain = one more lap on these tyres minus the first lap on a fresh set." })] })), panel === "review" && review && (_jsxs("div", { "data-testid": "race-review", children: [reviewObj ? (_jsxs(_Fragment, { children: [_jsxs(MetricRow, { children: [_jsx(Metric, { label: "Actual race", value: reviewObj.actual_time != null ? formatRaceTime(reviewObj.actual_time) : "incomplete", sub: reviewObj.actual.label, testId: "review-actual" }), _jsx(Metric, { label: "Model of that plan", value: formatRaceTime(reviewObj.model_actual_time) }), _jsx(Metric, { label: "Strategy cost", value: _jsxs("span", { className: reviewObj.strategy_cost_s > 0.05 ? "bad" : undefined, children: [fmtSigned(reviewObj.strategy_cost_s, 1), " s"] }), title: "Model time of the plan you ran minus the model optimum." }), _jsx(Metric, { label: "Execution vs model", value: reviewObj.execution_s != null ? `${fmtSigned(reviewObj.execution_s, 1)} s` : "—", title: "Actual time minus the model for the plan you ran (includes start lap, traffic, driving)." })] }), _jsx(ReviewNotes, { review: reviewObj, params: p, codes: data.specs })] })) : (_jsx("p", { className: "note", children: review.reason ?? "Open a race session (with pit stops) to compare the strategy that was run with the model optimum." })), review.game_pit_windows.length > 0 && (_jsxs("p", { className: "note", children: ["Game's pit window during the race (ideal\u2013latest lap): ", review.game_pit_windows.map(([a, b]) => `L${a}–${b}`).join(" → ")] }))] }))] })] }))] }))] }));
}
function SpecInput({ value, step, min, label, onChange }) {
    return (_jsx("input", { type: "number", step: step, min: min, style: { width: 84 }, value: Number(value.toFixed(3)), "aria-label": label, onChange: (e) => e.target.value !== "" && onChange(Number(e.target.value)) }));
}
function PlansTable({ plans }) {
    const columns = [
        { key: "n", header: "#", align: "right", render: (p) => p.rank },
        { key: "plan", header: "Plan", render: (p) => p.label },
        { key: "stops", header: "Stops", align: "right", render: (p) => p.stops },
        { key: "box", header: "Box lap (window)", render: (p) => windowsText(p.stop_laps, p.windows) },
        { key: "time", header: "Race time", align: "right", render: (p) => formatRaceTime(p.race_time) },
        { key: "delta", header: "Δ best (s)", align: "right", render: (p) => fmt(p.delta_best, 1) },
    ];
    return _jsx(DataTable, { testId: "plans-table", columns: columns, rows: plans.map((p, i) => ({ ...p, rank: i + 1 })), rowKey: (p) => p.rank });
}
function ReviewNotes({ review, params, codes }) {
    const notes = [];
    if (review.missing_laps.length)
        notes.push(`the export is missing lap(s) ${review.missing_laps.join(", ")}, so the total race time is unknown`);
    if (review.sc_laps.length)
        notes.push(`safety-car lap(s) ${review.sc_laps.join(", ")} are left out of the execution delta`);
    for (const o of review.over_limit) {
        const label = codes.find((c) => c.code === o.compound)?.label ?? String(o.compound);
        notes.push(`stint ${o.stint} ran ${o.laps} laps on ${label}, past the ${params.wear_limit_pct.toFixed(0)}% wear limit (model max ${o.max_laps}) — raise the limit to compare like for like`);
    }
    if (!notes.length)
        return null;
    return _jsxs("p", { className: "note", children: ["Note: ", notes.join("; "), "."] });
}
