/** Small presentational building blocks. */
import type { ReactNode } from "react"
import { ApiError } from "../api/client"
import "./ui.css"

export function Metric({ label, value, sub, title, testId }: { label: string; value: ReactNode; sub?: ReactNode; title?: string; testId?: string }) {
  return (
    <div className="metric" title={title} data-testid={testId}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {sub != null && sub !== "" && <div className="metric-sub">{sub}</div>}
    </div>
  )
}

export function MetricRow({ children }: { children: ReactNode }) {
  return <div className="metric-row">{children}</div>
}

export function Panel({ title, children, actions, testId, className }: { title?: ReactNode; children: ReactNode; actions?: ReactNode; testId?: string; className?: string }) {
  return (
    <section className={className ? `panel ${className}` : "panel"} data-testid={testId}>
      {(title || actions) && (
        <header className="panel-head">
          <h3>{title}</h3>
          <div className="panel-actions">{actions}</div>
        </header>
      )}
      {children}
    </section>
  )
}

export function Loading({ what = "Loading…" }: { what?: string }) {
  return <div className="loading">{what}</div>
}

export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof ApiError ? `${error.status}: ${error.message}` : error instanceof Error ? error.message : String(error)
  return (
    <div className="error-box" role="alert">
      {msg}
    </div>
  )
}

export interface Column<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  align?: "left" | "right"
  title?: string
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  rowClass,
  testId,
  maxHeight,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T, i: number) => string | number
  onRowClick?: (row: T) => void
  rowClass?: (row: T) => string | undefined
  testId?: string
  maxHeight?: number
}) {
  return (
    <div className="table-wrap" style={maxHeight ? { maxHeight } : undefined}>
      <table className="data" data-testid={testId}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.align === "right" ? "num" : undefined} title={c.title}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)} className={[onRowClick ? "clickable" : "", rowClass?.(row) ?? ""].join(" ").trim() || undefined} onClick={onRowClick ? () => onRowClick(row) : undefined}>
              {columns.map((c) => (
                <td key={c.key} className={c.align === "right" ? "num" : undefined}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Table over loosely-typed records (sensitivity / race calls): columns follow the first row's keys. */
export function RecordTable({ rows, formats, testId, maxHeight }: { rows: Record<string, string | number | boolean | null>[]; formats?: Record<string, (v: number) => string>; testId?: string; maxHeight?: number }) {
  if (!rows.length) return <p className="note">Nothing to show.</p>
  const keys = Object.keys(rows[0])
  const columns: Column<Record<string, string | number | boolean | null>>[] = keys.map((k) => ({
    key: k,
    header: k,
    align: typeof rows[0][k] === "number" ? "right" : "left",
    render: (r) => {
      const v = r[k]
      if (v == null) return "—"
      if (typeof v === "number") return formats?.[k] ? formats[k](v) : Number.isInteger(v) ? v : v.toFixed(2)
      return String(v)
    },
  }))
  return <DataTable columns={columns} rows={rows} rowKey={(_, i) => i} testId={testId} maxHeight={maxHeight} />
}
