/** Reference-lap choice shared by the Laps and Corners tabs: none, a lap in this session, or a lap of another session of the same track. */
import { useEffect, useMemo, useState } from "react"
import { useSession, useSessions } from "../api/hooks"
import type { LapSummary, SessionDetail, SessionMeta } from "../api/types"
import { formatLapTime } from "../lib/format"
import { bestLapNumber, lapLabel, pbSession } from "../lib/sessions"

export type RefMode = "none" | "lap" | "session"

export function LapSelect({ laps, value, onChange, label }: { laps: LapSummary[]; value: number | null; onChange: (lap: number) => void; label: string }) {
  return (
    <label className="field">
      {label}
      <select value={value ?? ""} onChange={(e) => onChange(Number(e.target.value))} aria-label={label}>
        {laps.map((l) => (
          <option key={l.lap} value={l.lap}>
            {lapLabel(l, formatLapTime)}
          </option>
        ))}
      </select>
    </label>
  )
}

export interface ReferenceChoice {
  mode: RefMode
  chooseMode: (m: RefMode) => void
  refLap: number | null
  setRefLap: (lap: number) => void
  refSessionId: number | null
  setRefSession: (id: number) => void
  sameTrack: SessionMeta[]
  pb: SessionMeta | null
  refLaps: LapSummary[]
  /** The chosen reference once it is complete (session null = this session), else null. */
  selection: { session: number | null; lap: number } | null
}

/** State of the reference pickers; resets to `initialMode` and the session's best lap when the session changes. */
export function useReference(detail: SessionDetail, initialMode: RefMode): ReferenceChoice {
  const { session, laps } = detail
  const sessions = useSessions()
  const best = bestLapNumber(laps)
  const [mode, setMode] = useState<RefMode>(initialMode)
  const [refLap, setRefLap] = useState<number | null>(best)
  const [refSessionId, setRefSessionId] = useState<number | null>(null)

  useEffect(() => {
    setMode(initialMode)
    setRefLap(bestLapNumber(laps))
    setRefSessionId(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id])

  const sameTrack = useMemo(() => (sessions.data ?? []).filter((s) => s.track === session.track && s.id !== session.id), [sessions.data, session.track, session.id])
  const pb = useMemo(() => pbSession(sessions.data?.filter((s) => s.track === session.track) ?? []), [sessions.data, session.track])
  const refDetail = useSession(refSessionId ?? 0, mode === "session" && refSessionId != null)
  const refLaps = mode === "session" ? (refDetail.data?.laps ?? []) : laps

  const chooseMode = (m: RefMode) => {
    setMode(m)
    if (m === "session") {
      const pick = pb && pb.id !== session.id ? pb.id : (sameTrack[0]?.id ?? null)
      setRefSessionId(pick)
      setRefLap(null) // filled once that session's laps arrive
    } else {
      setRefSessionId(null)
      setRefLap(best)
    }
  }
  useEffect(() => {
    if (mode === "session" && refDetail.data && (refLap == null || !refDetail.data.laps.some((l) => l.lap === refLap))) {
      setRefLap(bestLapNumber(refDetail.data.laps))
    }
  }, [mode, refDetail.data, refLap])

  const selection = useMemo(() => {
    if (mode === "none" || refLap == null || (mode === "session" && (!refDetail.data || refSessionId == null))) return null
    return { session: mode === "session" ? refSessionId : null, lap: refLap }
  }, [mode, refLap, refDetail.data, refSessionId])

  return {
    mode,
    chooseMode,
    refLap,
    setRefLap,
    refSessionId,
    setRefSession: (id) => {
      setRefSessionId(id)
      setRefLap(null)
    },
    sameTrack,
    pb,
    refLaps,
    selection,
  }
}

/** The reference selects (type, session, lap); `modes` lists the reference types on offer. */
export function ReferenceFields({ choice, modes }: { choice: ReferenceChoice; modes: RefMode[] }) {
  const { mode, chooseMode, refSessionId, setRefSession, sameTrack, pb, refLaps, refLap, setRefLap } = choice
  const names: Record<RefMode, string> = { none: "None", lap: "Lap in this session", session: "Another session" }
  return (
    <>
      <label className="field">
        Reference
        <select value={mode} onChange={(e) => chooseMode(e.target.value as RefMode)} aria-label="Reference type">
          {modes.map((m) => (
            <option key={m} value={m} disabled={m === "session" && sameTrack.length === 0}>
              {names[m]}
            </option>
          ))}
        </select>
      </label>
      {mode === "session" && (
        <label className="field">
          Reference session
          <select value={refSessionId ?? ""} onChange={(e) => setRefSession(Number(e.target.value))} aria-label="Reference session">
            {sameTrack.map((s) => (
              <option key={s.id} value={s.id}>
                #{s.id} · {s.session_type || "—"} · {s.lap_count} laps · best {formatLapTime(s.best_lap_time)}
                {pb?.id === s.id ? " ★ PB" : ""}
              </option>
            ))}
          </select>
        </label>
      )}
      {mode !== "none" && refLaps.length > 0 && <LapSelect laps={refLaps} value={refLap} onChange={setRefLap} label="Reference lap" />}
    </>
  )
}
