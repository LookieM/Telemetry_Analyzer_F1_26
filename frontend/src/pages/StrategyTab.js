import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { useReview } from "../api/hooks";
import { ErrorBox, Loading } from "../components/ui";
import { StrategyView } from "./StrategyView";
export function StrategyTab({ detail }) {
    const [override, setOverride] = useState(null);
    const review = useReview(detail.session.id, override);
    const track = review.data?.track ?? detail.session.track;
    const state = override ?? review.data?.state ?? null;
    return (_jsxs("div", { "data-testid": "strategy-tab", children: [review.isLoading && _jsx(Loading, { what: "Loading strategy\u2026" }), review.isError && _jsx(ErrorBox, { error: review.error }), !track && !review.isLoading && _jsx("p", { className: "note", children: "Track unknown for this session \u2014 use the Planner." }), track && state && _jsx(StrategyView, { track: track, state: state, onStateChange: setOverride, review: review.data })] }));
}
