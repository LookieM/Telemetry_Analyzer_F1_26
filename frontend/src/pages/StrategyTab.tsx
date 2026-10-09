import { useState } from "react"
import { useReview } from "../api/hooks"
import type { SessionDetail } from "../api/types"
import { ErrorBox, Loading } from "../components/ui"
import { StrategyView } from "./StrategyView"

export function StrategyTab({ detail }: { detail: SessionDetail }) {
  const [override, setOverride] = useState<string | null>(null)
  const review = useReview(detail.session.id, override)
  const track = review.data?.track ?? detail.session.track
  const state = override ?? review.data?.state ?? null

  return (
    <div data-testid="strategy-tab">
      {review.isLoading && <Loading what="Loading strategy…" />}
      {review.isError && <ErrorBox error={review.error} />}
      {!track && !review.isLoading && <p className="note">Track unknown for this session — use the Planner.</p>}
      {track && state && <StrategyView track={track} state={state} onStateChange={setOverride} review={review.data} />}
    </div>
  )
}
