import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router-dom";
import { useDeleteSession, usePatchSession, useSession } from "../api/hooks";
import { ErrorBox, Loading, Panel } from "../components/ui";
import { SESSION_TYPES, TRACK_STATES, TYRE_STATE_LABEL } from "../lib/constants";
import { formatBytes, formatLapTime } from "../lib/format";
import { bestLapNumber } from "../lib/sessions";
import "./Setups.css";
import { CoachTab } from "./CoachTab";
import { CornersTab } from "./CornersTab";
import { LapsTab } from "./LapsTab";
import { StrategyTab } from "./StrategyTab";
import { TyresTab } from "./TyresTab";
const TABS = [
    { key: "laps", label: "Laps" },
    { key: "corners", label: "Corners" },
    { key: "tyres", label: "Tyres" },
    { key: "strategy", label: "Strategy" },
    { key: "coach", label: "Coach" },
];
function TagsEditor({ session, trackState }) {
    const patch = usePatchSession();
    const del = useDeleteSession();
    const navigate = useNavigate();
    const [type, setType] = useState(session.session_type);
    const [state, setState] = useState(trackState.state);
    const [conditionNotes, setConditionNotes] = useState(trackState.notes);
    const [notes, setNotes] = useState(session.notes);
    useEffect(() => {
        setType(session.session_type);
        setState(trackState.state);
        setConditionNotes(trackState.notes);
        setNotes(session.notes);
    }, [session.id, session.session_type, trackState.state, trackState.notes, session.notes]);
    return (_jsxs(Panel, { title: "Session details", testId: "session-details", children: [_jsxs("div", { className: "row", children: [_jsxs("label", { className: "field", children: ["Session type", _jsxs("select", { value: type, onChange: (e) => setType(e.target.value), children: [_jsx("option", { value: "", children: "(untagged)" }), SESSION_TYPES.map((t) => (_jsx("option", { children: t }, t)))] })] }), _jsxs("label", { className: "field", children: ["Track state", _jsx("select", { value: state, onChange: (e) => setState(e.target.value), "aria-label": "Track state", children: TRACK_STATES.map((s) => (_jsx("option", { value: s, children: TYRE_STATE_LABEL[s] }, s))) })] }), _jsxs("label", { className: "field", children: ["Conditions notes", _jsx("input", { value: conditionNotes, onChange: (e) => setConditionNotes(e.target.value), placeholder: "drizzle, drying line \u2026" })] }), _jsxs("label", { className: "field", style: { flex: 1, minWidth: 220 }, children: ["Notes", _jsx("input", { value: notes, onChange: (e) => setNotes(e.target.value) })] }), _jsx("button", { className: "primary", disabled: patch.isPending, onClick: () => patch.mutate({ id: session.id, session_type: type, track_state: state, condition_notes: conditionNotes, notes }), children: "Save tags & notes" }), _jsx("button", { className: "danger", onClick: () => {
                            if (window.confirm(`Delete session #${session.id} from the library?`))
                                del.mutate(session.id, { onSuccess: () => navigate("/") });
                        }, children: "Delete session" })] }), patch.isError && _jsx(ErrorBox, { error: patch.error }), _jsxs("p", { className: "note", children: ["Original CSV ", formatBytes(session.original_size_bytes), " \u2192 library ", formatBytes(session.stored_size_bytes), session.setup_fingerprint ? ` · setup fingerprint ${session.setup_fingerprint}` : "", " \u00B7 source ", session.source_name] })] }));
}
export function SessionPage() {
    const params = useParams();
    const id = Number(params.id);
    const tab = (TABS.find((t) => t.key === params.tab)?.key ?? "laps");
    const detail = useSession(id);
    const [focusLap, setFocusLap] = useState(null);
    const [showDetails, setShowDetails] = useState(false);
    const laps = detail.data?.laps;
    const best = useMemo(() => (laps ? bestLapNumber(laps) : null), [laps]);
    useEffect(() => {
        setFocusLap(best);
    }, [id, best]);
    if (!Number.isFinite(id))
        return _jsx("p", { children: "Invalid session id." });
    if (detail.isLoading)
        return _jsx(Loading, { what: "Loading session\u2026" });
    if (detail.isError || !detail.data)
        return _jsx(ErrorBox, { error: detail.error ?? "Session not found" });
    const { session, track_state: trackState } = detail.data;
    return (_jsxs("div", { className: "stack", children: [_jsxs("div", { className: "page-head", children: [_jsxs("h1", { "data-testid": "session-title", children: [_jsxs("span", { className: "session-id", children: ["#", session.id, " \u00B7"] }), " ", session.track ?? "?"] }), session.session_type && _jsx("span", { className: "tag", children: session.session_type }), _jsxs("span", { className: "session-meta", children: [_jsx("span", { children: session.car ?? "?" }), _jsxs("span", { children: [session.lap_count, " laps"] }), _jsxs("span", { children: ["best", " ", _jsx("b", { className: "session-best", children: formatLapTime(session.best_lap_time) })] }), session.conditions && _jsx("span", { children: session.conditions })] }), _jsx("span", { className: "spacer" }), session.track && (_jsx(Link, { className: "button", to: `/track/${encodeURIComponent(session.track)}/setups`, title: "Compare the setups driven on this track", children: "Setups" })), _jsx("button", { onClick: () => setShowDetails((v) => !v), children: showDetails ? "Hide details" : "Details" })] }), trackState?.banner && (_jsx("p", { className: "note weather-banner", "data-testid": "weather-banner", children: trackState.banner })), showDetails && _jsx(TagsEditor, { session: session, trackState: trackState }), _jsx("nav", { className: "tabs", children: TABS.map((t) => (_jsx(NavLink, { to: `/session/${id}/${t.key}`, className: ({ isActive }) => (isActive || (t.key === tab && !params.tab) ? "active" : undefined), children: t.label }, t.key))) }), tab === "laps" && _jsx(LapsTab, { detail: detail.data, focusLap: focusLap, setFocusLap: setFocusLap }), tab === "corners" && _jsx(CornersTab, { detail: detail.data, focusLap: focusLap, setFocusLap: setFocusLap }), tab === "tyres" && _jsx(TyresTab, { detail: detail.data, focusLap: focusLap, setFocusLap: setFocusLap }), tab === "strategy" && _jsx(StrategyTab, { detail: detail.data }), tab === "coach" && _jsx(CoachTab, { detail: detail.data })] }));
}
