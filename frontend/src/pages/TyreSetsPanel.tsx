/** "Your tyre sets" in the strategy view: what the plan is limited to (game snapshot or your own list). */
import { useState } from "react"
import { useClearTyreSets, useSaveTyreSets } from "../api/hooks"
import type { CompoundSpec, TyreInventoryPayload } from "../api/types"
import { ErrorBox, Panel } from "../components/ui"

interface Row {
  compound: number
  wear: number
}

const SOURCE: Record<string, string> = { game: "from the game", manual: "set by you" }

function when(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: "short", timeStyle: "short" })
}

function wearList(used: number[]): string {
  return used.map((w) => `${Math.round(w)}%`).join(", ")
}

interface Props {
  track: string
  inventory: TyreInventoryPayload | null
  specs: CompoundSpec[]
  useInventory: boolean
  onUseInventory: (v: boolean) => void
}

export function TyreSetsPanel({ track, inventory, specs, useInventory, onUseInventory }: Props) {
  const [rows, setRows] = useState<Row[] | null>(null)
  const save = useSaveTyreSets()
  const clear = useClearTyreSets()
  const colorOf = (code: number) => specs.find((s) => s.code === code)?.color ?? "#8A9099"

  const startEdit = () => {
    const from = (inventory?.sets ?? []).filter((s) => s.available).map((s) => ({ compound: s.compound, wear: Math.round(s.wear) }))
    setRows(from.length ? from : specs.map((s) => ({ compound: s.code, wear: 0 })))
  }
  const setRow = (i: number, edit: Partial<Row>) => setRows((r) => (r ?? []).map((x, j) => (j === i ? { ...x, ...edit } : x)))
  const options = [...new Map([...specs.map((s) => [s.code, s.label] as const), ...(rows ?? []).map((r) => [r.compound, specs.find((s) => s.code === r.compound)?.label ?? `#${r.compound}`] as const)])]

  const actions = rows ? (
    <>
      <button className="primary" disabled={save.isPending} onClick={() => save.mutate({ track, sets: rows }, { onSuccess: () => setRows(null) })} data-testid="tyre-sets-save">
        Save sets
      </button>
      <button className="ghost" onClick={() => setRows(null)}>
        Cancel
      </button>
    </>
  ) : (
    <>
      <button onClick={startEdit} data-testid="tyre-sets-edit">
        {inventory ? "Edit sets" : "Add my sets"}
      </button>
      {inventory && (
        <button className="ghost" disabled={clear.isPending} onClick={() => clear.mutate(track)} title="Forget the sets: the plan treats every set as new and unlimited.">
          Clear
        </button>
      )}
    </>
  )

  return (
    <Panel title="Your tyre sets" actions={actions}>
      <div data-testid="tyre-sets">
        {rows ? (
          <div className="stack" style={{ gap: 6 }}>
            {rows.map((r, i) => (
              <div className="row" key={i} style={{ gap: 8 }}>
                <span className="chip" style={{ background: colorOf(r.compound) }} />
                <select value={r.compound} onChange={(e) => setRow(i, { compound: Number(e.target.value) })} aria-label={`Set ${i + 1} compound`}>
                  {options.map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                </select>
                <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  wear %
                  <input type="number" min={0} max={100} step={1} style={{ width: 70 }} value={r.wear} aria-label={`Set ${i + 1} wear`} onChange={(e) => e.target.value !== "" && setRow(i, { wear: Math.max(0, Math.min(100, Number(e.target.value))) })} />
                </label>
                <button className="ghost" onClick={() => setRows((x) => (x ?? []).filter((_, j) => j !== i))} aria-label={`Remove set ${i + 1}`}>
                  ✕
                </button>
              </div>
            ))}
            <div>
              <button className="ghost" onClick={() => setRows((x) => [...(x ?? []), { compound: specs[0]?.code ?? 18, wear: 0 }])}>
                + Add set
              </button>
            </div>
            <p className="note">0% = a new set. List only the sets you can still fit. The next game snapshot of this track replaces your list.</p>
          </div>
        ) : inventory ? (
          <>
            <div className="row" style={{ gap: 16 }}>
              {Object.entries(inventory.by_compound).map(([code, c]) => (
                <span key={code} title={c.in_model ? undefined : "This compound is not in the model for this track state, so the plan cannot use it."}>
                  <span className="chip" style={{ background: colorOf(Number(code)) }} />
                  <b>{c.label}</b> {c.new > 0 ? `${c.new} new` : ""}
                  {c.new > 0 && c.used.length ? " · " : ""}
                  {c.used.length ? `used ${wearList(c.used)}` : ""}
                  {!c.in_model && <span className="dim"> (not in model)</span>}
                </span>
              ))}
              {Object.keys(inventory.by_compound).length === 0 && <span className="dim">no set available</span>}
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                <input type="checkbox" checked={useInventory} onChange={(e) => onUseInventory(e.target.checked)} aria-label="Plan with my sets" data-testid="use-inventory" />
                Plan with my sets
              </label>
              <span className="note">
                {SOURCE[inventory.source] ?? inventory.source}
                {inventory.session_type ? ` · ${inventory.session_type}` : ""} · {when(inventory.updated_at)}
                {useInventory && !inventory.used ? " · track allocation unknown, so the sets cannot be matched — the plan uses unlimited new sets" : ""}
                {!useInventory ? " · off: the plan treats every set as new and unlimited" : ""}
              </span>
            </div>
          </>
        ) : (
          <p className="note">
            No tyre sets known for this track, so the plan treats every set as new and unlimited. The app reads them from the game while it runs during a session (e.g. qualifying), or add them
            here.
          </p>
        )}
        {(save.isError || clear.isError) && <ErrorBox error={save.error ?? clear.error} />}
      </div>
    </Panel>
  )
}
