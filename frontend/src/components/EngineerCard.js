import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/** Live page: the race engineer card (optometrist-style setup test). All decisions are server-side; this renders the view. */
import { useState } from "react";
import { ApiError, baselineApi, engineerApi } from "../api/client";
import { engineerBaselineName, offerSummary } from "../lib/baseline";
import { MAX_TAGS, PHASE_LABEL, buildAnswer, commandError, confidenceLabel, cornerRowLine, engineerPanel, fmtBudget, fmtDelta, stopwatchLine, tagCheckLine, tagLabel, toggleTag, validateAnswer, variantValue } from "../lib/engineer";
import { duelShown } from "../lib/duelLive";
import { DuelPanel, DuelStart } from "./DuelPanel";
import "./EngineerCard.css";
function Start({ run, busy }) {
    return (_jsxs("div", { className: "eg-start", "data-testid": "eg-start", children: [_jsx("p", { className: "dim", children: "Optometrist-style setup test for practice: you drive two variants, say which felt better, it checks the stopwatch." }), _jsxs("div", { className: "eg-verdict two", children: [_jsxs("button", { type: "button", className: "eg-big", disabled: busy, onClick: () => void run(() => engineerApi.start("short")), "data-testid": "eg-start-short", children: ["Short", _jsx("small", { children: "\u2248 18 min \u00B7 1 parameter" })] }), _jsxs("button", { type: "button", className: "eg-big", disabled: busy, onClick: () => void run(() => engineerApi.start("full")), "data-testid": "eg-start-full", children: ["Full", _jsx("small", { children: "\u2248 50 min \u00B7 3 parameters" })] })] }), _jsx(DuelStart, { run: run, busy: busy })] }));
}
function Result({ r }) {
    const roles = r.roles;
    return (_jsxs("div", { className: "eg-result", "data-testid": "eg-result", children: [_jsxs("div", { className: `eg-sw ${r.measurable ? (r.stopwatch_winner === "2" ? "v2" : "v1") : "none"}`, children: [_jsx("b", { children: stopwatchLine(r) }), _jsxs("span", { className: "dim", children: [confidenceLabel(r.confidence), " \u00B7 laps ", r.n["1"], " vs ", r.n["2"], r.deg_s_per_lap != null ? ` · tyre wear correction ${fmtDelta(r.deg_s_per_lap, 3)} s/lap` : ""] })] }), r.sectors.length > 0 && (_jsxs("div", { className: "eg-sectors", children: [r.sectors.map((s) => (_jsxs("span", { className: s.delta_s < 0 ? "fast" : "slow", children: ["S", s.sector, " ", _jsx("b", { children: fmtDelta(s.delta_s, 3) })] }, s.sector))), _jsx("span", { className: "dim", children: "(variant 2 minus 1)" })] })), !!r.corners?.length && (_jsxs("div", { className: "eg-corners", "data-testid": "eg-corners", children: [r.corners.map((c) => (_jsx("div", { className: c.delta_s < 0 ? "fast" : "slow", children: cornerRowLine(c) }, `${c.corner}-${c.phase}`))), _jsx("span", { className: "dim", children: "(variant 2 minus 1)" })] })), !!r.tag_check?.length && (_jsx("div", { className: "eg-tagcheck", "data-testid": "eg-tagcheck", children: r.tag_check.map((t) => {
                    const l = tagCheckLine(t);
                    return (_jsxs("div", { className: l.cls, children: [l.mark, " ", l.text] }, t.tag));
                }) })), r.agreement_text && _jsx("div", { className: `eg-agree ${r.agreement ?? ""}`, children: r.agreement_text }), roles && (_jsxs("div", { className: "eg-roles dim", children: ["Variant 1 was the ", _jsx("b", { children: roles["1"] ?? "?" }), ", Variant 2 the ", _jsx("b", { children: roles["2"] ?? "?" })] }))] }));
}
function QuestionForm({ v, run, busy }) {
    const [verdict, setVerdict] = useState(null);
    const [strength, setStrength] = useState("clear");
    const [tags, setTags] = useState([]);
    const [note, setNote] = useState("");
    const problem = validateAnswer({ verdict, strength, tags }, v.question.tags);
    const label = v.param?.label ?? "this pair";
    return (_jsxs("div", { className: "eg-question", "data-testid": "eg-question", children: [_jsxs("div", { className: "eg-q-title", children: ["Back in the garage: which felt better", v.param ? ` (${label})` : "", "?"] }), _jsx("div", { className: "eg-verdict", children: ["1", "2", "same"].map((x) => (_jsxs("button", { type: "button", className: `eg-big ${verdict === x ? "on" : ""}`, onClick: () => setVerdict(x), "aria-pressed": verdict === x, "data-testid": `eg-v-${x}`, children: [x === "same" ? "Same" : x, x !== "same" && v.variant_text && _jsx("small", { children: variantValue(v, x) })] }, x))) }), _jsxs("div", { className: "eg-strength", role: "group", "aria-label": "Strength", children: [["slight", "clear"].map((x) => (_jsx("button", { type: "button", className: `eg-seg ${strength === x ? "on" : ""}`, onClick: () => setStrength(x), "aria-pressed": strength === x, "data-testid": `eg-s-${x}`, children: x === "slight" ? "Slightly" : "Clearly" }, x))), _jsxs("span", { className: "dim eg-count", children: ["tags ", tags.length, "/", MAX_TAGS] })] }), _jsx("div", { className: "eg-tags", "data-testid": "eg-tags", children: v.question.tags.map((t) => {
                    const on = tags.includes(t);
                    const full = !on && tags.length >= MAX_TAGS;
                    return (_jsx("button", { type: "button", className: `eg-tag ${on ? "on" : ""}`, disabled: full, onClick: () => setTags(toggleTag(tags, t)), "aria-pressed": on, children: tagLabel(t) }, t));
                }) }), _jsxs("div", { className: "eg-submit", children: [_jsx("input", { className: "eg-note", type: "text", placeholder: "Optional note (what you felt)", maxLength: 200, value: note, onChange: (e) => setNote(e.target.value), "aria-label": "Note" }), _jsx("button", { type: "button", className: "eg-go", disabled: busy || problem != null, title: problem ?? "Send your answer", onClick: () => verdict && void run(() => engineerApi.answer(buildAnswer({ verdict, strength, tags, note }))), "data-testid": "eg-submit", children: "Submit" })] }), problem && verdict == null && _jsx("div", { className: "dim eg-hint", children: problem })] }));
}
function Confirm({ v, run, busy }) {
    const proposed = v.question.proposed;
    const roles = v.last_result?.roles;
    return (_jsxs("div", { className: "eg-confirm", "data-testid": "eg-confirm", children: [v.last_result && _jsx(Result, { r: v.last_result }), _jsx("div", { className: "eg-q-title", children: "Which variant becomes the new baseline?" }), _jsx("div", { className: "eg-verdict two", children: ["1", "2"].map((x) => (_jsxs("button", { type: "button", className: `eg-big ${proposed === x ? "on" : ""}`, disabled: busy, onClick: () => void run(() => engineerApi.confirm(x)), "data-testid": `eg-confirm-${x}`, children: ["Keep ", x, _jsxs("small", { children: [variantValue(v, x), roles?.[x] ? ` · ${roles[x]}` : "", proposed === x ? " · your answer" : ""] })] }, x))) })] }));
}
function Revert({ v, run, busy }) {
    const r = v.revert_proposal;
    return (_jsxs("div", { className: "eg-revert", "data-testid": "eg-revert", children: [_jsxs("div", { className: "eg-q-title", children: ["Parc ferm\u00E9: revert ", r.label, "?"] }), _jsx("p", { children: r.text }), _jsxs("div", { className: "eg-verdict two", children: [_jsxs("button", { type: "button", className: "eg-big on", disabled: busy, onClick: () => void run(() => engineerApi.revert(true)), "data-testid": "eg-revert-yes", children: ["Revert to ", String(r.to)] }), _jsxs("button", { type: "button", className: "eg-big", disabled: busy, onClick: () => void run(() => engineerApi.revert(false)), "data-testid": "eg-revert-no", children: ["Keep ", String(r.from)] })] })] }));
}
function RunPanel({ v }) {
    const r = v.run;
    const quali = v.phase === "quali";
    return (_jsxs("div", { className: "eg-run", "data-testid": "eg-run", children: [_jsx("div", { className: "eg-instruction", "data-testid": "eg-instruction", children: v.instruction ?? "Waiting for the next instruction…" }), v.variant_text && (_jsx("div", { className: "eg-variants", children: ["1", "2"].map((x) => (_jsxs("div", { className: `eg-var ${r.variant === x ? "now" : ""} ${v.detected.variant === x ? "det" : ""}`, children: [_jsx("span", { className: "eg-var-n", children: x }), _jsx("span", { className: "eg-var-t", children: variantValue(v, x) }), _jsxs("span", { className: "eg-var-c", children: [r.counted[x], "/", r.target] }), r.variant === x && _jsx("span", { className: "tag good", children: "drive now" }), v.detected.variant === x && _jsx("span", { className: "tag", children: "on car" })] }, x))) })), _jsxs("div", { className: "eg-progress", children: [r.variant ? (_jsxs(_Fragment, { children: ["Variant ", _jsx("b", { children: r.variant }), ": lap ", _jsx("b", { children: Math.min(r.lap + 1, r.target) }), " of ", r.target] })) : quali ? ("Quali laps counted") : ("Back to the garage"), !v.in_garage ? _jsx("span", { className: "dim", children: " \u00B7 on track" }) : _jsx("span", { className: "dim", children: " \u00B7 in garage" })] }), v.detected.warning && _jsx("div", { className: "eg-warn", "data-testid": "eg-warning", children: v.detected.warning }), v.tyre_hint && _jsx("div", { className: "eg-hint", children: v.tyre_hint })] }));
}
function BaselineOffer({ v }) {
    const offer = v.baseline_offer;
    const [state, setState] = useState("idle");
    if (!offer || !v.track)
        return null;
    const make = async () => {
        setState("busy");
        try {
            await baselineApi.set(v.track, { setup: offer.final, source: "engineer", name: engineerBaselineName() });
            setState("done");
        }
        catch {
            setState("error");
        }
    };
    return (_jsxs("div", { className: "eg-offer", "data-testid": "eg-offer", children: [_jsxs("div", { className: "eg-hint", children: ["Changed in this test: ", offerSummary(offer)] }), state === "done" ? (_jsxs("div", { className: "eg-hint", "data-testid": "eg-offer-done", children: ["Saved as the ", v.track, " baseline (see the Setups page)."] })) : (_jsx("button", { type: "button", className: "eg-ctl", disabled: state === "busy", onClick: () => void make(), "data-testid": "eg-make-baseline", children: "Make this the track baseline" })), state === "error" && _jsx("div", { className: "eg-error", role: "alert", children: "Could not save the baseline" })] }));
}
function LongRun({ v }) {
    const lr = v.long_run;
    const laps = lr?.laps ?? [];
    return (_jsxs("div", { className: "eg-long", "data-testid": "eg-long", children: [_jsx("div", { className: "eg-instruction", children: v.instruction ?? (v.phase === "done" ? "Program finished" : "Long run") }), lr && (_jsxs(_Fragment, { children: [_jsxs("div", { className: "eg-progress", children: [lr.label ?? "Race compound", ": ", _jsx("b", { children: laps.length }), " of ", lr.target, " laps", lr.wear_pct_per_lap != null && (_jsxs(_Fragment, { children: [" ", "\u00B7 wear ", _jsxs("b", { children: [lr.wear_pct_per_lap.toFixed(1), "%"] }), "/lap"] })), lr.pace_deg_s_per_lap != null && (_jsxs(_Fragment, { children: [" ", "\u00B7 pace ", _jsx("b", { children: fmtDelta(lr.pace_deg_s_per_lap, 3) }), " s/lap"] }))] }), laps.length > 0 && (_jsxs("table", { className: "eg-laps", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Lap" }), _jsx("th", { children: "Time" }), _jsx("th", { children: "Fuel-corr." }), _jsx("th", { children: "Wear" })] }) }), _jsx("tbody", { children: laps.slice(-6).map((l) => (_jsxs("tr", { children: [_jsx("td", { children: l.lap }), _jsx("td", { children: l.time_s != null ? l.time_s.toFixed(3) : "—" }), _jsx("td", { children: l.corrected_s != null ? l.corrected_s.toFixed(3) : "—" }), _jsx("td", { children: l.wear_pct != null ? `${l.wear_pct.toFixed(0)}%` : "—" })] }, l.lap))) })] }))] }))] }));
}
function History({ rows, settled }) {
    const done = Object.values(settled);
    if (!rows.length && !done.length)
        return null;
    return (_jsxs("details", { className: "eg-history", "data-testid": "eg-history", children: [_jsxs("summary", { children: ["History \u00B7 ", rows.length, " ", rows.length === 1 ? "pair" : "pairs", done.length > 0 && _jsxs("span", { className: "dim", children: [" \u00B7 settled: ", done.map((s) => `${s.label} ${s.value}`).join(", ")] })] }), _jsx("ul", { children: rows.map((h) => (_jsxs("li", { children: [_jsx("b", { children: h.label }), " ", h.variants ? Object.values(h.variants).join(" vs ") : "", " \u2192", " ", h.outcome === "skipped" ? "skipped" : h.winner ? `${h.winner_role ?? `variant ${h.winner}`} won` : h.outcome, h.delta_s != null && _jsxs("span", { className: "dim", children: [" \u00B7 ", fmtDelta(h.delta_s, 3), " s/lap"] }), h.your_answer && _jsxs("span", { className: "dim", children: [" \u00B7 you: ", h.your_answer.verdict === "same" ? "same" : `variant ${h.your_answer.verdict}`] })] }, h.n))) })] }));
}
export function EngineerCard({ view, duel }) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const run = async (fn) => {
        setBusy(true);
        setError(null);
        try {
            await fn();
        }
        catch (e) {
            setError(commandError(e instanceof ApiError ? e.status : null, e instanceof Error ? e.message : String(e)));
        }
        finally {
            setBusy(false);
        }
    };
    const panel = engineerPanel(view);
    const v = view && view.phase !== "idle" ? view : null;
    const active = v != null && v.phase !== "done";
    if (duelShown(duel) && !active) {
        return (_jsxs("section", { className: "lv-card eg-card panel-duel", "data-testid": "engineer-card", children: [_jsxs("div", { className: "eg-head", children: [_jsx("h3", { children: "Setup duel" }), _jsx("span", { className: "eg-phase", "data-testid": "dl-phase", children: duel.phase === "running" ? "Driving" : duel.phase === "review" ? "Ranking" : "Finished" }), _jsxs("span", { className: "eg-param", children: [duel.n, " setups ", _jsxs("span", { className: "dim", children: ["\u00B7 ", duel.track] })] })] }), _jsx(DuelPanel, { v: duel, run: run, busy: busy }), duel.phase === "done" && _jsx(Start, { busy: busy, run: run }), error && (_jsx("div", { className: "eg-error", role: "alert", "data-testid": "eg-error", children: error }))] }));
    }
    return (_jsxs("section", { className: `lv-card eg-card panel-${panel}`, "data-testid": "engineer-card", children: [_jsxs("div", { className: "eg-head", children: [_jsx("h3", { children: "Race engineer" }), v && (_jsxs(_Fragment, { children: [_jsx("span", { className: "eg-phase", "data-testid": "eg-phase", children: PHASE_LABEL[v.phase] ?? v.phase }), v.param && v.phase === "balance" && (_jsxs("span", { className: "eg-param", children: [v.param.label, " ", _jsxs("span", { className: "dim", children: ["(", v.param.index, " of ", v.param.of, ")"] })] })), _jsx("span", { className: "lv-spacer" }), active && (_jsxs("span", { className: "eg-budget", title: "Time left in this program", "data-testid": "eg-budget", children: [fmtBudget(v.budget.left_s), " left"] }))] }))] }), panel === "start" && _jsx(Start, { busy: busy, run: run }), panel === "revert" && v && _jsx(Revert, { v: v, run: run, busy: busy }), panel === "confirm" && v && _jsx(Confirm, { v: v, run: run, busy: busy }), panel === "question" && v && _jsx(QuestionForm, { v: v, run: run, busy: busy }, v.history.length), (panel === "run" || panel === "quali") && v && _jsx(RunPanel, { v: v }), (panel === "long_run" || panel === "done") && v && _jsx(LongRun, { v: v }), panel === "done" && v && _jsx(BaselineOffer, { v: v }), panel === "done" && _jsx(Start, { busy: busy, run: run }), error && (_jsx("div", { className: "eg-error", role: "alert", "data-testid": "eg-error", children: error })), v && v.feed.length > 0 && (_jsx("ul", { className: "eg-feed", "data-testid": "eg-feed", children: v.feed
                    .slice(-5)
                    .reverse()
                    .map((f, i) => (_jsx("li", { className: i === 0 ? "new" : "", children: f.text }, `${f.t}-${i}`))) })), v && _jsx(History, { rows: v.history, settled: v.settled }), v && (_jsxs("div", { className: "eg-controls", children: [active && v.phase === "balance" && (_jsx("button", { type: "button", className: "eg-ctl", disabled: busy, onClick: () => void run(engineerApi.skip), "data-testid": "eg-skip", children: "Skip parameter" })), active && (_jsx("button", { type: "button", className: "eg-ctl", disabled: busy, onClick: () => void run(engineerApi.nextPhase), "data-testid": "eg-next", children: "Next phase" })), _jsx("span", { className: "lv-spacer" }), active && (_jsx("button", { type: "button", className: "eg-ctl stop", disabled: busy, onClick: () => void run(engineerApi.stop), "data-testid": "eg-stop", children: "Stop" }))] }))] }));
}
