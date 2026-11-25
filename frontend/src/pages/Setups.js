import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useGeneratedSetup, useNameSetup, useRunDuel, useSetBaseline, useTrackBaseline, useTrackCatalog, useTrackProfile, useTrackSetups } from "../api/hooks";
import { DataTable, ErrorBox, Loading, Panel } from "../components/ui";
import { copyText, copyToClipboard, groupValues, sourceLabel, valueText } from "../lib/baseline";
import { confidenceClass, confidenceText, evidenceItemText, evidenceText, generatedBaselineRequest, profileRows, profileSourceLabel } from "../lib/generator";
import { balanceCell, balanceDistance, canRank, gapVsLeader, pickHint, setupLabel, togglePick, verdict, wearText } from "../lib/duel";
import { fmt, formatDate, formatLapTime } from "../lib/format";
import "./Setups.css";
/** /setups: jump to the first track that has sessions. */
export function SetupsIndex() {
    const catalog = useTrackCatalog();
    if (catalog.isLoading)
        return _jsx(Loading, {});
    const first = catalog.data?.tracks.find((t) => t.sessions > 0);
    if (!first)
        return _jsx("p", { className: "note", children: "No sessions in the library yet, so there are no setups to compare." });
    return _jsx(Navigate, { to: `/track/${encodeURIComponent(first.track)}/setups`, replace: true });
}
function NameEditor({ setup, track }) {
    const rename = useNameSetup(track);
    const [text, setText] = useState(setup.name ?? "");
    useEffect(() => setText(setup.name ?? ""), [setup.name]);
    const save = () => {
        if (text.trim() !== (setup.name ?? ""))
            rename.mutate({ fingerprint: setup.fingerprint, name: text });
    };
    return (_jsx("input", { className: "setup-name", value: text, placeholder: setupLabel({ fingerprint: setup.fingerprint, name: null }), maxLength: 60, "aria-label": "Setup name", onChange: (e) => setText(e.target.value), onBlur: save, onKeyDown: (e) => e.key === "Enter" && e.target.blur() }));
}
const RUN_COLUMNS = [
    { key: "session", header: "Session", render: (r) => _jsxs(Link, { to: `/session/${r.session_id}/laps`, children: ["#", r.session_id] }) },
    { key: "type", header: "Type", render: (r) => (r.session_type ? _jsx("span", { className: "tag", children: r.session_type }) : _jsx("span", { className: "dim", children: "\u2014" })) },
    { key: "laps", header: "Laps", render: (r) => `${r.first_lap}–${r.last_lap}` },
    { key: "clean", header: "Clean", align: "right", title: "Clean laps counted in a duel (no in / out / pit / invalid laps, no big mistakes)", render: (r) => `${r.n_clean}/${r.n_laps}` },
    { key: "compound", header: "Compound", render: (r) => r.compound_label },
    { key: "state", header: "Track", render: (r) => r.state },
    { key: "fuel", header: "Fuel", align: "right", render: (r) => (r.fuel_kg != null ? `${fmt(r.fuel_kg, 0)} kg` : "—") },
    { key: "pace", header: "Pace", align: "right", title: "Median fuel-corrected clean lap", render: (r) => formatLapTime(r.pace_s) },
    { key: "best", header: "Best", align: "right", render: (r) => formatLapTime(r.best_s) },
    { key: "wear", header: "Wear", align: "right", render: (r) => wearText(r.wear_pct_per_lap) },
];
function SetupCard({ setup, track, picked, onToggle, onBaseline }) {
    const [open, setOpen] = useState(false);
    return (_jsxs("div", { className: `setup-card${picked ? " picked" : ""}`, "data-testid": "setup-card", children: [_jsxs("div", { className: "setup-head", children: [_jsx("label", { className: "setup-pick", title: "Pick for a duel", children: _jsx("input", { type: "checkbox", checked: picked, onChange: onToggle, "aria-label": `Pick ${setupLabel(setup)}` }) }), _jsx(NameEditor, { setup: setup, track: track }), _jsx("span", { className: "dim mono", children: setup.fingerprint.slice(0, 8) }), _jsxs("span", { className: "dim", children: [setup.n_runs, " run", setup.n_runs === 1 ? "" : "s", " \u00B7 ", setup.n_clean, " clean laps \u00B7 last driven ", formatDate(setup.last_driven)] }), _jsx("span", { className: "spacer" }), setup.runs.length > 0 && (_jsx("button", { className: "ghost", title: "Use this setup (from its latest session) as the track baseline", onClick: () => onBaseline({ session_id: setup.runs[0].session_id, name: setupLabel(setup) }), "data-testid": "make-baseline-setup", children: "Make baseline" })), _jsx("button", { className: "ghost", onClick: () => setOpen((v) => !v), children: open ? "Hide runs" : "Runs" })] }), open && _jsx(DataTable, { columns: RUN_COLUMNS, rows: setup.runs, rowKey: (r) => `${r.session_id}-${r.run}` })] }));
}
function BaselineCard({ track, baseline, loading, error, saveError, onRestore }) {
    const [copied, setCopied] = useState(null);
    const active = baseline?.active ?? null;
    const older = (baseline?.history ?? []).filter((h) => !h.active);
    const copy = async () => {
        if (!active)
            return;
        setCopied((await copyToClipboard(copyText(`${track} baseline: ${active.name}`, active.display))) ? "ok" : "fail");
        window.setTimeout(() => setCopied(null), 2500);
    };
    return (_jsxs(Panel, { title: "Track baseline", testId: "baseline-card", actions: active && (_jsx("button", { className: "ghost", onClick: () => void copy(), "data-testid": "copy-baseline", children: copied === "ok" ? "Copied" : copied === "fail" ? "Copy failed" : "Copy as text" })), children: [loading && _jsx(Loading, { what: "Reading the baseline\u2026" }), error != null && _jsx(ErrorBox, { error: error }), saveError != null && _jsx(ErrorBox, { error: saveError }), baseline && !active && _jsx("p", { className: "note", children: "No baseline for this track yet. Make one from a duel winner, a setup below, or when the engineer finishes a program." }), active && (_jsxs(_Fragment, { children: [_jsxs("p", { className: "baseline-meta", "data-testid": "baseline-meta", children: [_jsx("b", { children: active.name }), " ", _jsx("span", { className: "tag", children: sourceLabel(active.source) }), " ", _jsxs("span", { className: "dim", children: ["set ", formatDate(active.created_at)] })] }), _jsx("div", { className: "baseline-groups", "data-testid": "baseline-values", children: groupValues(active.display).map((g) => (_jsxs("div", { className: "baseline-group", children: [_jsx("h4", { children: g.group }), _jsx("dl", { children: g.items.map((it) => (_jsxs("div", { className: "baseline-row", children: [_jsx("dt", { children: it.label }), _jsx("dd", { className: "mono", children: valueText(it) })] }, it.key))) })] }, g.group))) })] })), older.length > 0 && (_jsxs("details", { className: "baseline-history", "data-testid": "baseline-history", children: [_jsxs("summary", { children: ["History \u00B7 ", older.length, " older"] }), _jsx("ul", { children: older.map((h) => (_jsxs("li", { children: [_jsx("b", { children: h.name }), " ", _jsx("span", { className: "tag", children: sourceLabel(h.source) }), " ", _jsx("span", { className: "dim", children: formatDate(h.created_at) }), _jsx("button", { className: "ghost", onClick: () => onRestore(h.id), "data-testid": `restore-baseline-${h.id}`, children: "Restore" })] }, h.id))) })] }))] }));
}
function ProfilePanel({ profile, loading, error }) {
    return (_jsxs(Panel, { title: "Track profile", testId: "profile-panel", actions: profile && _jsx("span", { className: "tag", "data-testid": "profile-source", children: profileSourceLabel(profile) }), children: [loading && _jsx(Loading, { what: "Reading the track\u2026" }), error != null && _jsx(ErrorBox, { error: error }), profile && (_jsxs(_Fragment, { children: [_jsx("dl", { className: "profile-rows", "data-testid": "profile-rows", children: profileRows(profile).map((r) => (_jsxs("div", { className: "baseline-row", children: [_jsx("dt", { children: r.label }), _jsx("dd", { className: "mono", children: r.text })] }, r.label))) }), _jsxs("p", { className: "note", children: [profile.source === "driven"
                                ? "Measured on your best clean lap of this track (corners and full-throttle distance)."
                                : "No lap of this track in the library: estimated from the catalogue's corner zones, so treat it as rough.", " ", "Tracks with a similar profile share their setup results."] })] }))] }));
}
function GeneratedRow({ item, entry }) {
    const [open, setOpen] = useState(false);
    return (_jsxs("div", { className: "gen-row-wrap", children: [_jsxs("button", { className: "gen-row", "aria-expanded": open, onClick: () => setOpen((v) => !v), "data-testid": `gen-row-${item.key}`, children: [_jsx("span", { className: "gen-label", children: item.label }), _jsx("span", { className: "mono", children: valueText(item) }), _jsx("span", { className: `badge dot ${confidenceClass(entry.confidence)}`, title: confidenceText(entry), "aria-label": confidenceText(entry), "data-testid": `gen-badge-${item.key}`, children: _jsx("span", { className: "sr-only", children: confidenceText(entry) }) })] }), open && (_jsxs("div", { className: "gen-evidence", "data-testid": `gen-evidence-${item.key}`, children: [_jsx("p", { children: evidenceText(entry) }), entry.note && _jsx("p", { className: "warn-text", children: entry.note }), entry.evidence.length > 0 && (_jsx("ul", { children: entry.evidence.map((e) => (_jsx("li", { children: evidenceItemText(entry, e) }, `${e.track}-${e.source}-${e.value}`))) }))] }))] }));
}
function GeneratedCard({ track, hasBaseline, onClose, onBaseline, saveError }) {
    const gen = useGeneratedSetup(track, true);
    const g = gen.data;
    return (_jsxs(Panel, { title: "Generated setup", testId: "generated-card", actions: _jsxs(_Fragment, { children: [hasBaseline && (_jsx("button", { className: "ghost", onClick: onClose, "data-testid": "hide-generated", children: "Hide generated" })), g && (_jsx("button", { className: "primary", onClick: () => onBaseline(generatedBaselineRequest(g)), "data-testid": "make-generated-baseline", children: "Make baseline" }))] }), children: [gen.isLoading && _jsx(Loading, { what: "Working out a starting setup\u2026" }), gen.isError && _jsx(ErrorBox, { error: gen.error }), saveError != null && _jsx(ErrorBox, { error: saveError }), g && (_jsxs(_Fragment, { children: [_jsxs("p", { className: "baseline-meta", "data-testid": "gen-summary", children: [_jsx("span", { children: "Overall confidence" }), _jsx("span", { className: `badge ${confidenceClass(g.overall_confidence)}`, "data-testid": "gen-overall", children: g.overall_confidence === "low" && g.evidence_tracks.length === 0 ? "Low – prior only" : g.overall_confidence }), _jsxs("span", { className: "dim", children: ["aero ", g.group_confidence.aero, " \u00B7 mechanical ", g.group_confidence.mechanical] }), _jsx("span", { className: "dim", children: g.evidence_tracks.length > 0 ? `from ${g.evidence_tracks.slice(0, 4).join(", ")}${g.evidence_tracks.length > 4 ? "…" : ""}` : `typical-setup table (${g.prior_source}) only` })] }), g.first_test && (_jsxs("p", { className: "first-test", "data-testid": "gen-first-test", children: [_jsxs("b", { children: [g.first_test.text, "."] }), " It is the one among wings, diff and anti-roll bars the evidence backs least."] })), _jsxs("p", { className: "note", "data-testid": "gen-fuel", children: ["Fuel: ", g.fuel.quali_kg, " kg for quali (game minimum), ", g.fuel.race_kg, " kg for the race (", g.fuel.kg_per_lap.toFixed(2), " kg/lap \u00D7 ", g.fuel.race_laps, " laps + 1; ", g.fuel.source, "). The setup carries the race fuel."] }), _jsx("div", { className: "baseline-groups", "data-testid": "gen-values", children: groupValues(g.display).map((grp) => (_jsxs("div", { className: "baseline-group", children: [_jsx("h4", { children: grp.group }), grp.items.map((it) => (_jsx(GeneratedRow, { item: it, entry: g.setup[it.key] }, it.key)))] }, grp.group))) }), _jsxs("p", { className: "gen-legend", "data-testid": "gen-legend", children: [_jsx("span", { className: "badge dot good" }), " measured / meta / high ", _jsx("span", { className: "badge dot warn" }), " medium ", _jsx("span", { className: "badge dot bad" }), " low, prior only"] }), _jsx("p", { className: "note", children: "Click a value to see where it came from. Camber stays at the meta; values are snapped to the garage steps and the suspension is kept coherent." })] }))] }));
}
function ResultTable({ result, onBaseline }) {
    const r = result.ranking;
    if (!r)
        return null;
    const columns = [
        { key: "rank", header: "#", align: "right", render: (c) => c.rank },
        { key: "name", header: "Setup", render: (c) => _jsx("b", { children: c.name }) },
        { key: "laps", header: "Laps", align: "right", render: (c) => c.n_laps },
        { key: "race", header: "Race pace", align: "right", title: "Mean of the corrected clean laps", render: (c) => formatLapTime(c.race_pace_s) },
        { key: "quali", header: "Quali pace", align: "right", title: "Best corrected lap", render: (c) => formatLapTime(c.quali_pace_s) },
        { key: "wear", header: "Wear", align: "right", render: (c) => wearText(c.wear_pct_per_lap) },
        { key: "cost", header: "Race cost", align: "right", title: "What its tyre wear costs per lap over a 50 % race, vs the gentlest setup", render: (c) => `${fmt(c.race_cost_s, 3)} s` },
        { key: "score", header: "Score", align: "right", title: `${Math.round(r.weights.race * 100)} % race pace + cost, ${Math.round(r.weights.quali * 100)} % one-lap pace`, render: (c) => formatLapTime(c.score_s) },
        {
            key: "gap",
            header: "vs leader",
            render: (c) => {
                const g = gapVsLeader(c, r.noise_s);
                return _jsx("span", { className: g.measurable === false ? "warn-text" : undefined, children: g.text });
            },
        },
        { key: "entry", header: "Entry", render: (c) => balanceCell(c.balance, "entry") },
        { key: "mid", header: "Mid", render: (c) => balanceCell(c.balance, "mid") },
        { key: "exit", header: "Exit", render: (c) => balanceCell(c.balance, "exit") },
        { key: "dist", header: "From neutral", align: "right", title: "Summed distance from neutral over the three phases", render: (c) => balanceDistance(c.balance) },
        {
            key: "base",
            header: "",
            render: (c) => result.duel_id != null ? (_jsx("button", { className: c.rank === 1 ? "primary" : "ghost", onClick: () => onBaseline({ duel_id: result.duel_id, winner_key: c.key, name: c.name }), "data-testid": `make-baseline-${c.rank}`, children: "Make baseline" })) : null,
        },
    ];
    return (_jsxs("div", { className: "stack", "data-testid": "duel-result", children: [_jsx("p", { className: "verdict", "data-testid": "duel-verdict", children: verdict(r) }), !r.same_session && (_jsxs("p", { className: "not-comparable", "data-testid": "cross-session", children: [r.callouts.find((t) => t.startsWith("Laps come from different sessions")) ?? "Laps come from different sessions.", " The noise band is widened to ", fmt(r.noise_s, 2), " s."] })), _jsx(DataTable, { columns: columns, rows: r.contestants, rowKey: (c) => c.key, testId: "duel-table", rowClass: (c) => (c.rank === 1 ? "leader-row" : undefined) }), _jsxs("p", { className: "note", children: ["Compared on ", result.condition?.compound_label, " \u00B7 ", result.condition?.state, " track \u00B7 noise band ", fmt(r.noise_s, 2), " s per lap", result.correction ? ` · fuel ${fmt(result.correction.fuel_s_per_kg * 1000, 0)} ms/kg, tyre age ${fmt(result.correction.deg_s_per_lap, 3)} s/lap (${result.correction.deg_source})` : "", ". Feel is only available in a live duel."] }), r.cost_note && _jsx("p", { className: `note${r.cost_source === "fallback" ? " warn-text" : ""}`, children: r.cost_note }), result.balance_note && _jsxs("p", { className: "note warn-text", children: ["Balance not measured: ", result.balance_note] }), r.callouts.length > 0 && (_jsx("ul", { className: "callouts", "data-testid": "duel-callouts", children: r.callouts.filter((t) => r.same_session || !t.startsWith("Laps come from different sessions")).map((t) => (_jsx("li", { children: t }, t))) }))] }));
}
function DuelPanel({ track, picked, setups, onBaseline }) {
    const duel = useRunDuel(track);
    const names = picked.map((fp) => setups.find((s) => s.fingerprint === fp)).filter((s) => !!s).map(setupLabel);
    const result = duel.data;
    return (_jsxs(Panel, { title: "Duel", testId: "duel-panel", actions: _jsxs(_Fragment, { children: [_jsx("span", { className: "dim", children: pickHint(picked.length) }), _jsx("button", { className: "primary", disabled: !canRank(picked) || duel.isPending, onClick: () => duel.mutate(picked), "data-testid": "rank-button", children: duel.isPending ? "Ranking…" : "Rank them" })] }), children: [picked.length > 0 && _jsxs("p", { className: "note", children: ["Picked: ", names.join(" · ")] }), duel.isError && _jsx(ErrorBox, { error: duel.error }), result && !result.comparable && (_jsxs("div", { className: "not-comparable", "data-testid": "not-comparable", children: [_jsx("b", { children: "Not comparable" }), _jsx("ul", { children: result.reasons.map((t) => (_jsx("li", { children: t }, t))) }), _jsxs("p", { className: "note", children: ["Setups are compared on clean laps of the same track condition and compound, at least ", result.min_clean_laps, " each."] })] })), result?.comparable && _jsx(ResultTable, { result: result, onBaseline: onBaseline }), !result && !duel.isPending && _jsx("p", { className: "note", children: "Ranks on 70 % race pace (fuel- and tyre-age-corrected, plus what its tyre wear costs over a 50 % race) and 30 % one-lap pace. Differences inside the noise are called a tie and balance decides." })] }));
}
export function SetupsPage() {
    const params = useParams();
    const track = params.track ?? "";
    const navigate = useNavigate();
    const catalog = useTrackCatalog();
    const setups = useTrackSetups(track);
    const baseline = useTrackBaseline(track);
    const setBaseline = useSetBaseline(track);
    const profile = useTrackProfile(track);
    const [picked, setPicked] = useState([]);
    const [showGenerated, setShowGenerated] = useState(false);
    useEffect(() => {
        setPicked([]);
        setShowGenerated(false);
    }, [track]);
    const hasBaseline = !!baseline.data?.active;
    const generatedOn = (!!baseline.data && !hasBaseline) || showGenerated;
    const all = catalog.data?.tracks ?? [];
    const list = setups.data?.setups ?? [];
    return (_jsxs("div", { className: "stack", "data-testid": "setups-page", children: [_jsxs("div", { className: "page-head", children: [_jsxs("h1", { children: ["Setups \u00B7 ", track] }), _jsxs("label", { className: "field inline", children: ["Track", _jsxs("select", { value: track, onChange: (e) => navigate(`/track/${encodeURIComponent(e.target.value)}/setups`), "aria-label": "Track", children: [!all.some((t) => t.track === track) && _jsx("option", { value: track, children: track }), all.map((t) => (_jsxs("option", { value: t.track, children: [t.track, t.sessions > 0 ? ` (${t.sessions})` : ""] }, t.track)))] })] })] }), _jsx(BaselineCard, { track: track, baseline: baseline.data, loading: baseline.isLoading, error: baseline.error, saveError: setBaseline.error, onRestore: (id) => setBaseline.mutate({ restore_id: id }) }), hasBaseline && !showGenerated && (_jsxs("p", { className: "note", children: [_jsx("button", { className: "ghost", onClick: () => setShowGenerated(true), "data-testid": "show-generated", children: "Show generated setup" }), " ", "A starting setup computed from similar tracks, for comparison with this baseline."] })), generatedOn && _jsx(GeneratedCard, { track: track, hasBaseline: hasBaseline, onClose: () => setShowGenerated(false), onBaseline: (b) => setBaseline.mutate(b), saveError: setBaseline.error }), _jsx(ProfilePanel, { profile: profile.data, loading: profile.isLoading, error: profile.error }), _jsxs(Panel, { title: "Setups driven here", testId: "setup-list", children: [setups.isLoading && _jsx(Loading, { what: "Reading the track's runs\u2026" }), setups.isError && _jsx(ErrorBox, { error: setups.error }), setups.data && list.length === 0 && _jsx("p", { className: "note", children: "No setups driven on this track in the library yet." }), list.length > 0 && _jsx("p", { className: "note", children: "Distinct mechanical setups (fuel does not count; different tyre pressures make a separate setup). Tick two or three to rank them, click a name to rename." }), list.map((s) => (_jsx(SetupCard, { setup: s, track: track, picked: picked.includes(s.fingerprint), onToggle: () => setPicked((p) => togglePick(p, s.fingerprint)), onBaseline: (b) => setBaseline.mutate(b) }, s.fingerprint)))] }), list.length > 0 && _jsx(DuelPanel, { track: track, picked: picked, setups: list, onBaseline: (b) => setBaseline.mutate(b) })] }));
}
