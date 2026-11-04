/** Coach: the session read and the engineer's ranked callouts over every probable lap (PB as the reference). */
import { useState } from "react"
import { useCoach } from "../api/hooks"
import type { CoachItem, SessionDetail } from "../api/types"
import { ErrorBox, Loading, Metric, MetricRow, Panel } from "../components/ui"
import { ACTION_LABEL, groupByDomain, titleCase } from "../lib/coach"
import { fmt } from "../lib/format"
import "./CoachTab.css"

function Callout({ item, showMeta = true }: { item: CoachItem; showMeta?: boolean }) {
  return (
    <li className={`callout ${item.action_kind} ${item.severity}`} data-testid="coach-callout">
      {showMeta && (
        <span className="callout-meta">
          {ACTION_LABEL[item.action_kind] ?? item.action_kind} · {item.domain}
        </span>
      )}
      <strong>{item.title}</strong>
      <span>{item.detail}</span>
    </li>
  )
}

export function CoachTab({ detail }: { detail: SessionDetail }) {
  const coach = useCoach(detail.session.id)
  const [showRest, setShowRest] = useState(false)

  if (coach.isLoading) return <Loading what="Reading the whole session…" />
  if (coach.isError || !coach.data) return <ErrorBox error={coach.error ?? "No coach feed"} />
  const { headline, diagnosis: d, top, rest } = coach.data

  return (
    <div className="stack" data-testid="coach-tab">
      <Panel title="Session read">
        <p className="coach-headline" data-testid="coach-headline">
          {headline}
        </p>
        <MetricRow>
          <Metric label="Balance" value={d.primary_issue === "balanced" ? "Balanced" : titleCase(d.primary_issue)} sub={d.primary_issue === "balanced" ? "" : `${d.phase} · ${d.strength}`} />
          <Metric label="Biggest corner loss" value={d.worst_corner ?? "—"} sub={d.worst_corner ? `+${fmt(d.worst_corner_loss_s, 3)} s` : ""} />
          <Metric label="Reference" value={d.ref_lap != null ? `L${d.ref_lap}` : "—"} sub={`read from L${d.focus_lap}`} />
          <Metric label="Confidence" value={`${Math.round(d.confidence * 100)}%`} />
        </MetricRow>
      </Panel>

      <Panel title="Top callouts" testId="coach-top">
        {top.length === 0 ? (
          <p className="note">No session callouts yet — it needs more probable laps or richer telemetry channels.</p>
        ) : (
          <ol className="callouts">
            {top.map((it) => (
              <Callout key={it.id} item={it} />
            ))}
          </ol>
        )}
      </Panel>

      {rest.length > 0 && (
        <Panel
          title={`More callouts (${rest.length})`}
          actions={
            <button onClick={() => setShowRest((v) => !v)} data-testid="coach-more">
              {showRest ? "Hide" : "Show"}
            </button>
          }
        >
          {showRest &&
            groupByDomain(rest).map((g) => (
              <div key={g.domain} className="callout-group">
                <h4>{titleCase(g.domain)}</h4>
                <ul className="callouts">
                  {g.items.map((it) => (
                    <Callout key={it.id} item={it} showMeta={false} />
                  ))}
                </ul>
              </div>
            ))}
        </Panel>
      )}
      <p className="note">Session-level feed from all probable laps with the best lap as the reference; the lap selectors of the other tabs do not change it.</p>
    </div>
  )
}
