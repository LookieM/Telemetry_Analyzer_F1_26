import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
/** Coach: the session read and the engineer's ranked callouts over every probable lap (PB as the reference). */
import { useState } from "react";
import { useCoach } from "../api/hooks";
import { ErrorBox, Loading, Metric, MetricRow, Panel } from "../components/ui";
import { ACTION_LABEL, groupByDomain, titleCase } from "../lib/coach";
import { fmt } from "../lib/format";
import "./CoachTab.css";
function Callout({ item, showMeta = true }) {
    return (_jsxs("li", { className: `callout ${item.action_kind} ${item.severity}`, "data-testid": "coach-callout", children: [showMeta && (_jsxs("span", { className: "callout-meta", children: [ACTION_LABEL[item.action_kind] ?? item.action_kind, " \u00B7 ", item.domain] })), _jsx("strong", { children: item.title }), _jsx("span", { children: item.detail })] }));
}
export function CoachTab({ detail }) {
    const coach = useCoach(detail.session.id);
    const [showRest, setShowRest] = useState(false);
    if (coach.isLoading)
        return _jsx(Loading, { what: "Reading the whole session\u2026" });
    if (coach.isError || !coach.data)
        return _jsx(ErrorBox, { error: coach.error ?? "No coach feed" });
    const { headline, diagnosis: d, top, rest } = coach.data;
    return (_jsxs("div", { className: "stack", "data-testid": "coach-tab", children: [_jsxs(Panel, { title: "Session read", children: [_jsx("p", { className: "coach-headline", "data-testid": "coach-headline", children: headline }), _jsxs(MetricRow, { children: [_jsx(Metric, { label: "Balance", value: d.primary_issue === "balanced" ? "Balanced" : titleCase(d.primary_issue), sub: d.primary_issue === "balanced" ? "" : `${d.phase} · ${d.strength}` }), _jsx(Metric, { label: "Biggest corner loss", value: d.worst_corner ?? "—", sub: d.worst_corner ? `+${fmt(d.worst_corner_loss_s, 3)} s` : "" }), _jsx(Metric, { label: "Reference", value: d.ref_lap != null ? `L${d.ref_lap}` : "—", sub: `read from L${d.focus_lap}` }), _jsx(Metric, { label: "Confidence", value: `${Math.round(d.confidence * 100)}%` })] })] }), _jsx(Panel, { title: "Top callouts", testId: "coach-top", children: top.length === 0 ? (_jsx("p", { className: "note", children: "No session callouts yet \u2014 it needs more probable laps or richer telemetry channels." })) : (_jsx("ol", { className: "callouts", children: top.map((it) => (_jsx(Callout, { item: it }, it.id))) })) }), rest.length > 0 && (_jsx(Panel, { title: `More callouts (${rest.length})`, actions: _jsx("button", { onClick: () => setShowRest((v) => !v), "data-testid": "coach-more", children: showRest ? "Hide" : "Show" }), children: showRest &&
                    groupByDomain(rest).map((g) => (_jsxs("div", { className: "callout-group", children: [_jsx("h4", { children: titleCase(g.domain) }), _jsx("ul", { className: "callouts", children: g.items.map((it) => (_jsx(Callout, { item: it, showMeta: false }, it.id))) })] }, g.domain))) })), _jsx("p", { className: "note", children: "Session-level feed from all probable laps with the best lap as the reference; the lap selectors of the other tabs do not change it." })] }));
}
