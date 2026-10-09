import { useMemo, useState } from "react"
import { useSessions } from "../api/hooks"
import { Panel } from "../components/ui"
import { StrategyView } from "./StrategyView"

export function Planner() {
  const sessions = useSessions()
  const tracks = useMemo(() => [...new Set((sessions.data ?? []).map((s) => s.track).filter((t): t is string => !!t))].sort(), [sessions.data])
  const [picked, setPicked] = useState<string | null>(null)
  const [state, setState] = useState("dry")
  const track = (picked ?? tracks[0] ?? "").trim()

  return (
    <div className="stack" data-testid="planner">
      <div className="page-head">
        <h1>Strategy planner</h1>
        <span className="dim">Any track in your library, or type a new one.</span>
      </div>
      <Panel>
        <div className="row">
          <label className="field">
            Track
            <input list="planner-tracks" value={picked ?? tracks[0] ?? ""} onChange={(e) => setPicked(e.target.value)} aria-label="Track" />
            <datalist id="planner-tracks">
              {tracks.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
          </label>
        </div>
      </Panel>
      {track && <StrategyView track={track} state={state} onStateChange={setState} />}
    </div>
  )
}
