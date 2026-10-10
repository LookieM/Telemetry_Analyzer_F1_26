import { useState } from "react"
import { useTrackCatalog } from "../api/hooks"
import type { CatalogTrack } from "../api/types"
import { Panel } from "../components/ui"
import { StrategyView } from "./StrategyView"

const SOURCE_LABEL: Record<string, string> = {
  manual: "set by you",
  game: "reported by the game",
  inferred: "seen in your sessions",
  "pirelli-2026": "real-world 2026 Pirelli nomination — the game often differs; replaced once you drive the track",
  none: "unknown — set it in Tyres or drive the track once",
}

function allocText(t: CatalogTrack): string {
  const a = t.allocation
  if (!a.soft && !a.medium && !a.hard) return SOURCE_LABEL.none
  return `S ${a.soft ?? "?"} · M ${a.medium ?? "?"} · H ${a.hard ?? "?"} — ${SOURCE_LABEL[a.source] ?? a.source}`
}

export function Planner() {
  const catalog = useTrackCatalog()
  const tracks = catalog.data?.tracks ?? []
  const raced = tracks.filter((t) => t.sessions > 0)
  const fresh = tracks.filter((t) => t.sessions === 0)
  const [picked, setPicked] = useState<string | null>(null)
  const [state, setState] = useState("dry")
  const track = picked ?? raced[0]?.track ?? tracks[0]?.track ?? ""
  const info = tracks.find((t) => t.track === track)
  const share = Math.round((catalog.data?.race_share ?? 0.5) * 100)

  return (
    <div className="stack" data-testid="planner">
      <div className="page-head">
        <h1>Strategy planner</h1>
        <span className="dim">Every F1 26 circuit · {share}% race distance</span>
      </div>
      <Panel>
        <div className="row">
          <label className="field">
            Track
            <select value={track} onChange={(e) => setPicked(e.target.value)} aria-label="Track" data-testid="planner-track">
              {raced.length > 0 && (
                <optgroup label="Raced">
                  {raced.map((t) => (
                    <option key={t.track} value={t.track}>
                      {t.track} · {t.sessions} session{t.sessions === 1 ? "" : "s"}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label="Not raced yet">
                {fresh.map((t) => (
                  <option key={t.track} value={t.track}>
                    {t.track}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
          {info && (
            <span className="dim" data-testid="planner-track-info">
              {info.race_laps ? `${share}% race: ${info.race_laps} laps (of ${info.full_laps})` : "race length unknown"}
              {info.length_m ? ` · ${(info.length_m / 1000).toFixed(3)} km` : ""} · tyres {allocText(info)}
            </span>
          )}
        </div>
      </Panel>
      {track && <StrategyView track={track} state={state} onStateChange={setState} />}
    </div>
  )
}
