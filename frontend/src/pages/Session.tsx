import { useEffect, useMemo, useState } from "react"
import { Link, NavLink, useNavigate, useParams } from "react-router-dom"
import { useDeleteSession, usePatchSession, useSession } from "../api/hooks"
import type { SessionMeta } from "../api/types"
import { ErrorBox, Loading, Panel } from "../components/ui"
import { SESSION_TYPES } from "../lib/constants"
import { formatBytes, formatLapTime } from "../lib/format"
import { bestLapNumber } from "../lib/sessions"
import "./Setups.css"
import { CornersTab } from "./CornersTab"
import { LapsTab } from "./LapsTab"
import { StrategyTab } from "./StrategyTab"
import { TyresTab } from "./TyresTab"

const TABS = [
  { key: "laps", label: "Laps" },
  { key: "corners", label: "Corners" },
  { key: "tyres", label: "Tyres" },
  { key: "strategy", label: "Strategy" },
] as const

function TagsEditor({ session }: { session: SessionMeta }) {
  const patch = usePatchSession()
  const del = useDeleteSession()
  const navigate = useNavigate()
  const [type, setType] = useState(session.session_type)
  const [conditions, setConditions] = useState(session.conditions)
  const [notes, setNotes] = useState(session.notes)
  useEffect(() => {
    setType(session.session_type)
    setConditions(session.conditions)
    setNotes(session.notes)
  }, [session.id, session.session_type, session.conditions, session.notes])

  return (
    <Panel title="Session details" testId="session-details">
      <div className="row">
        <label className="field">
          Session type
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">(untagged)</option>
            {SESSION_TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Conditions
          <input value={conditions} onChange={(e) => setConditions(e.target.value)} placeholder="Dry (blank) / Damp - drizzle …" />
        </label>
        <label className="field" style={{ flex: 1, minWidth: 220 }}>
          Notes
          <input value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <button className="primary" disabled={patch.isPending} onClick={() => patch.mutate({ id: session.id, session_type: type, conditions, notes })}>
          Save tags &amp; notes
        </button>
        <button
          className="danger"
          onClick={() => {
            if (window.confirm(`Delete session #${session.id} from the library?`)) del.mutate(session.id, { onSuccess: () => navigate("/") })
          }}
        >
          Delete session
        </button>
      </div>
      {patch.isError && <ErrorBox error={patch.error} />}
      <p className="note">
        Original CSV {formatBytes(session.original_size_bytes)} → library {formatBytes(session.stored_size_bytes)}
        {session.setup_fingerprint ? ` · setup fingerprint ${session.setup_fingerprint}` : ""} · source {session.source_name}
      </p>
    </Panel>
  )
}

export function SessionPage() {
  const params = useParams()
  const id = Number(params.id)
  const tab = (TABS.find((t) => t.key === params.tab)?.key ?? "laps") as (typeof TABS)[number]["key"]
  const detail = useSession(id)
  const [focusLap, setFocusLap] = useState<number | null>(null)
  const [showDetails, setShowDetails] = useState(false)

  const laps = detail.data?.laps
  const best = useMemo(() => (laps ? bestLapNumber(laps) : null), [laps])
  useEffect(() => {
    setFocusLap(best)
  }, [id, best])

  if (!Number.isFinite(id)) return <p>Invalid session id.</p>
  if (detail.isLoading) return <Loading what="Loading session…" />
  if (detail.isError || !detail.data) return <ErrorBox error={detail.error ?? "Session not found"} />
  const { session } = detail.data

  return (
    <div className="stack">
      <div className="page-head">
        <h1 data-testid="session-title">
          <span className="session-id">#{session.id} ·</span> {session.track ?? "?"}
        </h1>
        {session.session_type && <span className="tag">{session.session_type}</span>}
        <span className="session-meta">
          <span>{session.car ?? "?"}</span>
          <span>{session.lap_count} laps</span>
          <span>
            best{" "}
            <b className="session-best">{formatLapTime(session.best_lap_time)}</b>
          </span>
          {session.conditions && <span>{session.conditions}</span>}
        </span>
        <span className="spacer" />
        {session.track && (
          <Link className="button" to={`/track/${encodeURIComponent(session.track)}/setups`} title="Compare the setups driven on this track">
            Setups
          </Link>
        )}
        <button onClick={() => setShowDetails((v) => !v)}>{showDetails ? "Hide details" : "Details"}</button>
      </div>
      {showDetails && <TagsEditor session={session} />}
      <nav className="tabs">
        {TABS.map((t) => (
          <NavLink key={t.key} to={`/session/${id}/${t.key}`} className={({ isActive }) => (isActive || (t.key === tab && !params.tab) ? "active" : undefined)}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      {tab === "laps" && <LapsTab detail={detail.data} focusLap={focusLap} setFocusLap={setFocusLap} />}
      {tab === "corners" && <CornersTab detail={detail.data} focusLap={focusLap} setFocusLap={setFocusLap} />}
      {tab === "tyres" && <TyresTab detail={detail.data} focusLap={focusLap} setFocusLap={setFocusLap} />}
      {tab === "strategy" && <StrategyTab detail={detail.data} />}
    </div>
  )
}
