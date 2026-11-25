import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDeleteSession, useImportFile, useLibraryStats, useSessions } from "../api/hooks";
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel } from "../components/ui";
import { SESSION_TYPES } from "../lib/constants";
import { formatBytes, formatDate, formatLapTime } from "../lib/format";
import { filterSessions } from "../lib/sessions";
import "./Setups.css";
import "./Library.css";
function ImportPanel() {
    const fileRef = useRef(null);
    const [type, setType] = useState("");
    const [conditions, setConditions] = useState("");
    const [notes, setNotes] = useState("");
    const imp = useImportFile();
    const navigate = useNavigate();
    const submit = () => {
        const file = fileRef.current?.files?.[0];
        if (!file)
            return;
        imp.mutate({ file, session_type: type, conditions, notes }, {
            onSuccess: (res) => {
                if (fileRef.current)
                    fileRef.current.value = "";
                const id = Number(res.session_id);
                if (Number.isFinite(id) && id > 0)
                    navigate(`/session/${id}/laps`);
            },
        });
    };
    return (_jsxs(Panel, { title: "Import an SRT CSV", testId: "import-panel", children: [_jsxs("div", { className: "row", children: [_jsxs("label", { className: "field", children: ["CSV file", _jsx("input", { ref: fileRef, type: "file", accept: ".csv,.tsv,text/csv", "data-testid": "import-file" })] }), _jsxs("label", { className: "field", children: ["Session type", _jsxs("select", { value: type, onChange: (e) => setType(e.target.value), children: [_jsx("option", { value: "", children: "(auto)" }), SESSION_TYPES.map((t) => (_jsx("option", { children: t }, t)))] })] }), _jsxs("label", { className: "field", children: ["Conditions", _jsx("input", { value: conditions, onChange: (e) => setConditions(e.target.value), placeholder: "e.g. Damp - drizzle" })] }), _jsxs("label", { className: "field", children: ["Notes", _jsx("input", { value: notes, onChange: (e) => setNotes(e.target.value) })] }), _jsx("button", { className: "primary", onClick: submit, disabled: imp.isPending, children: imp.isPending ? "Importing…" : "Import" })] }), imp.isError && _jsx(ErrorBox, { error: imp.error }), imp.isSuccess && _jsx("p", { className: "note", children: "Imported." })] }));
}
export function Library() {
    const sessions = useSessions();
    const stats = useLibraryStats();
    const del = useDeleteSession();
    const navigate = useNavigate();
    const [track, setTrack] = useState("");
    const [type, setType] = useState("");
    const [query, setQuery] = useState("");
    const [showImport, setShowImport] = useState(false);
    const all = sessions.data ?? [];
    const tracks = useMemo(() => [...new Set(all.map((s) => s.track).filter((t) => !!t))].sort(), [all]);
    const rows = useMemo(() => filterSessions(all, { track, type, query }), [all, track, type, query]);
    const columns = [
        { key: "id", header: "#", align: "right", render: (s) => s.id },
        { key: "date", header: "Imported", render: (s) => formatDate(s.created_at) },
        { key: "track", header: "Track", render: (s) => s.track ?? "?" },
        { key: "type", header: "Type", render: (s) => (s.session_type ? _jsx("span", { className: "tag", children: s.session_type }) : _jsx("span", { className: "dim", children: "\u2014" })) },
        { key: "car", header: "Car", render: (s) => s.car ?? "?" },
        { key: "laps", header: "Laps", align: "right", render: (s) => s.lap_count },
        { key: "best", header: "Best lap", align: "right", render: (s) => formatLapTime(s.best_lap_time) },
        { key: "size", header: "Stored", align: "right", render: (s) => formatBytes(s.stored_size_bytes) },
        { key: "source", header: "Source file", render: (s) => _jsx("span", { className: "dim cell-clip", title: s.source_name, children: s.source_name }) },
        { key: "notes", header: "Notes", render: (s) => {
                const text = [s.conditions, s.notes].filter(Boolean).join(" · ");
                return _jsx("span", { className: "dim cell-clip", title: text, children: text });
            },
        },
        {
            key: "del",
            header: "",
            render: (s) => (_jsx("button", { className: "ghost danger lib-del", title: "Delete this session from the library", onClick: (e) => {
                    e.stopPropagation();
                    if (window.confirm(`Delete session #${s.id} (${s.source_name}) from the library?`))
                        del.mutate(s.id);
                }, children: "Delete" })),
        },
    ];
    return (_jsxs("div", { className: "stack", children: [_jsxs("div", { className: "page-head", children: [_jsx("h1", { children: "Library" }), _jsx("span", { className: "spacer" }), _jsx("button", { onClick: () => setShowImport((v) => !v), children: showImport ? "Hide import" : "Import CSV" })] }), stats.data && (_jsxs(MetricRow, { children: [_jsx(Metric, { label: "Sessions", value: stats.data.sessions, testId: "stat-sessions" }), _jsx(Metric, { label: "Tracks", value: stats.data.tracks }), _jsx(Metric, { label: "Stored", value: formatBytes(stats.data.stored_bytes), sub: `from ${formatBytes(stats.data.original_bytes)} of CSV` }), _jsx(Metric, { label: "Space saved", value: formatBytes(stats.data.saved_bytes) })] })), showImport && _jsx(ImportPanel, {}), _jsx(Panel, { className: "toolbar", children: _jsxs("div", { className: "row", children: [_jsxs("label", { className: "field", children: ["Track", _jsxs("select", { value: track, onChange: (e) => setTrack(e.target.value), "aria-label": "Filter track", children: [_jsx("option", { value: "", children: "All tracks" }), tracks.map((t) => (_jsx("option", { children: t }, t)))] })] }), _jsxs("label", { className: "field", children: ["Type", _jsxs("select", { value: type, onChange: (e) => setType(e.target.value), "aria-label": "Filter session type", children: [_jsx("option", { value: "", children: "All types" }), SESSION_TYPES.map((t) => (_jsx("option", { children: t }, t))), _jsx("option", { value: "(untagged)", children: "(untagged)" })] })] }), _jsxs("label", { className: "field lib-search", children: ["Search", _jsx("input", { placeholder: "File, car, notes\u2026", value: query, onChange: (e) => setQuery(e.target.value), "aria-label": "Search sessions" })] }), _jsx("span", { className: "spacer" }), track && (_jsxs(Link, { className: "button", to: `/track/${encodeURIComponent(track)}/setups`, title: "Compare the setups you have driven here", children: ["Setups for ", track] }))] }) }), _jsxs(Panel, { title: "Sessions", actions: _jsx("span", { className: "dim mono", children: rows.length === all.length ? rows.length : `${rows.length} / ${all.length}` }), children: [sessions.isLoading && _jsx(Loading, {}), sessions.isError && _jsx(ErrorBox, { error: sessions.error }), del.isError && _jsx(ErrorBox, { error: del.error }), sessions.data && rows.length === 0 && _jsx("p", { className: "note", children: all.length ? "No sessions match these filters." : "Library is empty. Import an SRT CSV." }), rows.length > 0 && (_jsx(DataTable, { testId: "sessions-table", columns: columns, rows: rows, rowKey: (s) => s.id, onRowClick: (s) => navigate(`/session/${s.id}/laps`) }))] })] }));
}
