import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { ApiError } from "../api/client";
import "./ui.css";
export function Metric({ label, value, sub, title, testId }) {
    return (_jsxs("div", { className: "metric", title: title, "data-testid": testId, children: [_jsx("div", { className: "metric-label", children: label }), _jsx("div", { className: "metric-value", children: value }), sub != null && sub !== "" && _jsx("div", { className: "metric-sub", children: sub })] }));
}
export function MetricRow({ children }) {
    return _jsx("div", { className: "metric-row", children: children });
}
export function Panel({ title, children, actions, testId, className }) {
    return (_jsxs("section", { className: className ? `panel ${className}` : "panel", "data-testid": testId, children: [(title || actions) && (_jsxs("header", { className: "panel-head", children: [_jsx("h3", { children: title }), _jsx("div", { className: "panel-actions", children: actions })] })), children] }));
}
export function Loading({ what = "Loading…" }) {
    return _jsx("div", { className: "loading", children: what });
}
export function ErrorBox({ error }) {
    const msg = error instanceof ApiError ? `${error.status}: ${error.message}` : error instanceof Error ? error.message : String(error);
    return (_jsx("div", { className: "error-box", role: "alert", children: msg }));
}
export function DataTable({ columns, rows, rowKey, onRowClick, rowClass, testId, maxHeight, }) {
    return (_jsx("div", { className: "table-wrap", style: maxHeight ? { maxHeight } : undefined, children: _jsxs("table", { className: "data", "data-testid": testId, children: [_jsx("thead", { children: _jsx("tr", { children: columns.map((c) => (_jsx("th", { className: c.align === "right" ? "num" : undefined, title: c.title, children: c.header }, c.key))) }) }), _jsx("tbody", { children: rows.map((row, i) => (_jsx("tr", { className: [onRowClick ? "clickable" : "", rowClass?.(row) ?? ""].join(" ").trim() || undefined, onClick: onRowClick ? () => onRowClick(row) : undefined, children: columns.map((c) => (_jsx("td", { className: c.align === "right" ? "num" : undefined, children: c.render(row) }, c.key))) }, rowKey(row, i)))) })] }) }));
}
/** Table over loosely-typed records (sensitivity / race calls): columns follow the first row's keys. */
export function RecordTable({ rows, formats, testId, maxHeight }) {
    if (!rows.length)
        return _jsx("p", { className: "note", children: "Nothing to show." });
    const keys = Object.keys(rows[0]);
    const columns = keys.map((k) => ({
        key: k,
        header: k,
        align: typeof rows[0][k] === "number" ? "right" : "left",
        render: (r) => {
            const v = r[k];
            if (v == null)
                return "—";
            if (typeof v === "number")
                return formats?.[k] ? formats[k](v) : Number.isInteger(v) ? v : v.toFixed(2);
            return String(v);
        },
    }));
    return _jsx(DataTable, { columns: columns, rows: rows, rowKey: (_, i) => i, testId: testId, maxHeight: maxHeight });
}
