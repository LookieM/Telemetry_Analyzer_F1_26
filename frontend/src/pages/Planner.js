import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { useTrackCatalog } from "../api/hooks";
import { Panel } from "../components/ui";
import { StrategyView } from "./StrategyView";
const SOURCE_LABEL = {
    manual: "set by you",
    game: "reported by the game",
    inferred: "seen in your sessions",
    "pirelli-2026": "real-world 2026 Pirelli nomination — the game often differs; replaced once you drive the track",
    none: "unknown — set it in Tyres or drive the track once",
};
function allocText(t) {
    const a = t.allocation;
    if (!a.soft && !a.medium && !a.hard)
        return SOURCE_LABEL.none;
    return `S ${a.soft ?? "?"} · M ${a.medium ?? "?"} · H ${a.hard ?? "?"} — ${SOURCE_LABEL[a.source] ?? a.source}`;
}
export function Planner() {
    const catalog = useTrackCatalog();
    const tracks = catalog.data?.tracks ?? [];
    const raced = tracks.filter((t) => t.sessions > 0);
    const fresh = tracks.filter((t) => t.sessions === 0);
    const [picked, setPicked] = useState(null);
    const [state, setState] = useState("dry");
    const track = picked ?? raced[0]?.track ?? tracks[0]?.track ?? "";
    const info = tracks.find((t) => t.track === track);
    const share = Math.round((catalog.data?.race_share ?? 0.5) * 100);
    return (_jsxs("div", { className: "stack", "data-testid": "planner", children: [_jsxs("div", { className: "page-head", children: [_jsx("h1", { children: "Strategy planner" }), _jsxs("span", { className: "dim", children: ["Every F1 26 circuit \u00B7 ", share, "% race distance"] })] }), _jsx(Panel, { className: "toolbar", children: _jsxs("div", { className: "row", children: [_jsxs("label", { className: "field", children: ["Track", _jsxs("select", { value: track, onChange: (e) => setPicked(e.target.value), "aria-label": "Track", "data-testid": "planner-track", children: [raced.length > 0 && (_jsx("optgroup", { label: "Raced", children: raced.map((t) => (_jsxs("option", { value: t.track, children: [t.track, " \u00B7 ", t.sessions, " session", t.sessions === 1 ? "" : "s"] }, t.track))) })), _jsx("optgroup", { label: "Not raced yet", children: fresh.map((t) => (_jsx("option", { value: t.track, children: t.track }, t.track))) })] })] }), info && (_jsxs("span", { className: "dim", "data-testid": "planner-track-info", children: [info.race_laps ? `${share}% race: ${info.race_laps} laps (of ${info.full_laps})` : "race length unknown", info.length_m ? ` · ${(info.length_m / 1000).toFixed(3)} km` : "", " \u00B7 tyres ", allocText(info)] }))] }) }), track && _jsx(StrategyView, { track: track, state: state, onStateChange: setState })] }));
}
