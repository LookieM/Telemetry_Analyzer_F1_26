import { useMemo, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useDeleteSession, useImportFile, useLibraryStats, useSessions } from "../api/hooks"
import type { SessionMeta } from "../api/types"
import { DataTable, ErrorBox, Loading, Metric, MetricRow, Panel, type Column } from "../components/ui"
import { SESSION_TYPES } from "../lib/constants"
import { formatBytes, formatDate, formatLapTime } from "../lib/format"
import { filterSessions } from "../lib/sessions"
import "./Setups.css"

function ImportPanel() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [type, setType] = useState("")
  const [conditions, setConditions] = useState("")
  const [notes, setNotes] = useState("")
  const imp = useImportFile()
  const navigate = useNavigate()

  const submit = () => {
    const file = fileRef.current?.files?.[0]
    if (!file) return
    imp.mutate(
      { file, session_type: type, conditions, notes },
      {
        onSuccess: (res) => {
          if (fileRef.current) fileRef.current.value = ""
          const id = Number(res.session_id)
          if (Number.isFinite(id) && id > 0) navigate(`/session/${id}/laps`)
        },
      },
    )
  }

  return (
    <Panel title="Import an SRT CSV" testId="import-panel">
      <div className="row">
        <label className="field">
          CSV file
          <input ref={fileRef} type="file" accept=".csv,.tsv,text/csv" data-testid="import-file" />
        </label>
        <label className="field">
          Session type
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">(auto)</option>
            {SESSION_TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Conditions
          <input value={conditions} onChange={(e) => setConditions(e.target.value)} placeholder="e.g. Damp - drizzle" />
        </label>
        <label className="field">
          Notes
          <input value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <button className="primary" onClick={submit} disabled={imp.isPending}>
          {imp.isPending ? "Importing…" : "Import"}
        </button>
      </div>
      {imp.isError && <ErrorBox error={imp.error} />}
      {imp.isSuccess && <p className="note">Imported.</p>}
    </Panel>
  )
}

export function Library() {
  const sessions = useSessions()
  const stats = useLibraryStats()
  const del = useDeleteSession()
  const navigate = useNavigate()
  const [track, setTrack] = useState("")
  const [type, setType] = useState("")
  const [query, setQuery] = useState("")
  const [showImport, setShowImport] = useState(false)

  const all = sessions.data ?? []
  const tracks = useMemo(() => [...new Set(all.map((s) => s.track).filter((t): t is string => !!t))].sort(), [all])
  const rows = useMemo(() => filterSessions(all, { track, type, query }), [all, track, type, query])

  const columns: Column<SessionMeta>[] = [
    { key: "id", header: "#", align: "right", render: (s) => s.id },
    { key: "date", header: "Imported", render: (s) => formatDate(s.created_at) },
    { key: "track", header: "Track", render: (s) => s.track ?? "?" },
    { key: "type", header: "Type", render: (s) => (s.session_type ? <span className="tag">{s.session_type}</span> : <span className="dim">—</span>) },
    { key: "car", header: "Car", render: (s) => s.car ?? "?" },
    { key: "laps", header: "Laps", align: "right", render: (s) => s.lap_count },
    { key: "best", header: "Best lap", align: "right", render: (s) => formatLapTime(s.best_lap_time) },
    { key: "size", header: "Stored", align: "right", render: (s) => formatBytes(s.stored_size_bytes) },
    { key: "source", header: "Source file", render: (s) => <span className="dim">{s.source_name}</span> },
    { key: "notes", header: "Notes", render: (s) => <span className="dim">{[s.conditions, s.notes].filter(Boolean).join(" · ")}</span> },
    {
      key: "del",
      header: "",
      render: (s) => (
        <button
          className="ghost danger"
          title="Delete this session from the library"
          onClick={(e) => {
            e.stopPropagation()
            if (window.confirm(`Delete session #${s.id} (${s.source_name}) from the library?`)) del.mutate(s.id)
          }}
        >
          Delete
        </button>
      ),
    },
  ]

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Library</h1>
        <span className="spacer" />
        <button onClick={() => setShowImport((v) => !v)}>{showImport ? "Hide import" : "Import CSV"}</button>
      </div>
      {stats.data && (
        <MetricRow>
          <Metric label="Sessions" value={stats.data.sessions} testId="stat-sessions" />
          <Metric label="Tracks" value={stats.data.tracks} />
          <Metric label="Stored" value={formatBytes(stats.data.stored_bytes)} sub={`from ${formatBytes(stats.data.original_bytes)} of CSV`} />
          <Metric label="Space saved" value={formatBytes(stats.data.saved_bytes)} />
        </MetricRow>
      )}
      {showImport && <ImportPanel />}
      <Panel
        title="Sessions"
        actions={
          <>
            {track && (
              <Link className="button" to={`/track/${encodeURIComponent(track)}/setups`} title="Compare the setups you have driven here">
                Setups for {track}
              </Link>
            )}
            <select value={track} onChange={(e) => setTrack(e.target.value)} aria-label="Filter track">
              <option value="">All tracks</option>
              {tracks.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Filter session type">
              <option value="">All types</option>
              {SESSION_TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
              <option value="(untagged)">(untagged)</option>
            </select>
            <input placeholder="Search file, car, notes…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search sessions" />
          </>
        }
      >
        {sessions.isLoading && <Loading />}
        {sessions.isError && <ErrorBox error={sessions.error} />}
        {del.isError && <ErrorBox error={del.error} />}
        {sessions.data && rows.length === 0 && <p className="note">{all.length ? "No sessions match these filters." : "Library is empty. Import an SRT CSV."}</p>}
        {rows.length > 0 && (
          <DataTable
            testId="sessions-table"
            columns={columns}
            rows={rows}
            rowKey={(s) => s.id}
            onRowClick={(s) => navigate(`/session/${s.id}/laps`)}
          />
        )}
      </Panel>
    </div>
  )
}
