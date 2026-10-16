/**
 * Track map on canvas: racing line coloured by a channel, hover readout with every channel (focus / ref / Δ),
 * click to pin, colour legend and corner labels. Port of telemetry/ui/assets/track_map.js; the cursor is shared
 * with the trace charts through the zustand cursor store (group = `sync`).
 */
import { useEffect, useId, useMemo, useRef, useState } from "react"
import type { MapPayload } from "../api/types"
import { scaleColor, scaleGradient } from "../lib/colors"
import { nearestIndex, selectGroup, useCursorStore } from "../lib/cursor"
import { fmt, fmtSigned } from "../lib/format"
import { nearestOnScreen, projectTrack, zoomMapPayload, type Projection } from "../lib/maplayout"
import "./TrackMap.css"

interface MapTheme {
  text: string
  bg: string
  border: string
  accent: string
  font: string
}

function readTheme(el: HTMLElement): MapTheme {
  const css = getComputedStyle(el)
  const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback
  return { text: v("--text", "#d8dde3"), bg: v("--bg", "#0d1014"), border: v("--border", "rgba(128,128,128,0.45)"), accent: v("--accent", "#e03c31"), font: v("--font-ui", "sans-serif") }
}

function dot(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, fill: string, stroke: string, lw: number) {
  ctx.beginPath()
  ctx.arc(x, y, r, 0, Math.PI * 2)
  ctx.fillStyle = fill
  ctx.fill()
  ctx.lineWidth = lw
  ctx.strokeStyle = stroke
  ctx.stroke()
}

/** Everything that does not move with the cursor: outline, coloured line, corner labels. */
function drawStatic(ctx: CanvasRenderingContext2D, data: MapPayload, proj: Projection, theme: MapTheme, w: number, h: number, marks: MapMark[]) {
  ctx.clearRect(0, 0, w, h)
  ctx.lineJoin = "round"
  ctx.lineCap = "round"
  if (proj.ox.length > 1) {
    ctx.save()
    ctx.globalAlpha = 0.28
    ctx.strokeStyle = theme.border
    ctx.lineWidth = 11
    ctx.beginPath()
    proj.ox.forEach((x, i) => (i ? ctx.lineTo(x, proj.oy[i]) : ctx.moveTo(x, proj.oy[i])))
    ctx.stroke()
    ctx.restore()
  }
  const c = data.color
  const lo = c ? c.min : 0
  const hi = c ? c.max : 1
  ctx.lineWidth = 3.5
  for (let i = 1; i < proj.px.length; i++) {
    if (!Number.isFinite(proj.px[i]) || !Number.isFinite(proj.px[i - 1])) continue
    const v = c ? c.values[i] : null
    ctx.strokeStyle = (v != null && c && scaleColor(c.scale, (v - lo) / Math.max(1e-9, hi - lo))) || theme.text
    ctx.beginPath()
    ctx.moveTo(proj.px[i - 1], proj.py[i - 1])
    ctx.lineTo(proj.px[i], proj.py[i])
    ctx.stroke()
  }
  ctx.font = `600 10px ${theme.font}`
  ctx.fillStyle = theme.text
  ctx.globalAlpha = 0.8
  for (const lab of data.labels) {
    const i = nearestIndex(data.d, lab.d)
    if (i >= 0 && Number.isFinite(proj.px[i])) ctx.fillText(lab.text, proj.px[i] + 7, proj.py[i] - 6)
  }
  ctx.globalAlpha = 1
  ctx.font = `600 11px ${theme.font}`
  for (const m of marks) {
    const i = nearestIndex(data.d, m.d)
    if (i < 0 || !Number.isFinite(proj.px[i])) continue
    dot(ctx, proj.px[i], proj.py[i], 5, m.color, theme.bg, 2)
    ctx.fillStyle = theme.text
    ctx.fillText(m.label, proj.px[i] + 8, proj.py[i] + 4)
  }
}

/** A labelled dot on the racing line at a lap distance (brake point, full-throttle point ...). */
export interface MapMark {
  d: number
  label: string
  color: string
}

interface Props {
  data: MapPayload
  sync: string
  title?: string
  height?: number
  /** Show only this distance window (the line is refitted to it); null / undefined shows the whole lap. */
  zoom?: [number, number] | null
  marks?: MapMark[]
}

export function TrackMap({ data: full, sync, title, height = 520, zoom = null, marks }: Props) {
  const zoomFrom = zoom?.[0]
  const zoomTo = zoom?.[1]
  const data = useMemo(() => (zoomFrom != null && zoomTo != null ? zoomMapPayload(full, [zoomFrom, zoomTo]) : full), [full, zoomFrom, zoomTo])
  const shownMarks = useMemo(() => marks ?? [], [marks])
  const wrapRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const staticRef = useRef<HTMLCanvasElement | null>(null)
  const id = useId()
  const [width, setWidth] = useState(0)
  const [hover, setHover] = useState<number | null>(null)
  const group = useCursorStore(selectGroup(sync))
  const setStoreHover = useCursorStore((s) => s.setHover)
  const setPinned = useCursorStore((s) => s.setPinned)

  const valid = data.x.length >= 2

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => setWidth(Math.max(280, el.clientWidth))
    update()
    const obs = new ResizeObserver(update)
    obs.observe(el)
    return () => obs.disconnect()
  }, [valid])

  const proj = useMemo(() => (width ? projectTrack(data.x, data.y, data.outline, width, height) : null), [data, width, height])

  const inView = (x: number) => data === full || (x >= (zoomFrom ?? -Infinity) && x <= (zoomTo ?? Infinity))
  const extIdx = group.hoverX != null && group.hoverSource !== id && inView(group.hoverX) ? nearestIndex(data.d, group.hoverX) : null
  const pinIdx = group.pinnedX != null && inView(group.pinnedX) ? nearestIndex(data.d, group.pinnedX) : null
  const liveIdx = hover ?? extIdx

  // Static layer, redrawn only when data / size / theme change.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !proj) return
    const dpr = devicePixelRatio || 1
    const layer = staticRef.current ?? (staticRef.current = document.createElement("canvas"))
    layer.width = Math.round(width * dpr)
    layer.height = Math.round(height * dpr)
    const ctx = layer.getContext("2d")
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    drawStatic(ctx, data, proj, readTheme(canvas), width, height, shownMarks)
    canvas.width = layer.width
    canvas.height = layer.height
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    canvas.dataset.ready = String(Date.now())
  }, [data, proj, width, height, shownMarks])

  // Cursor dots on top of the cached static layer.
  useEffect(() => {
    const canvas = canvasRef.current
    const layer = staticRef.current
    if (!canvas || !layer || !proj || canvas.width !== layer.width) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    const dpr = devicePixelRatio || 1
    const t = readTheme(canvas)
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(layer, 0, 0)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    if (pinIdx != null && Number.isFinite(proj.px[pinIdx])) dot(ctx, proj.px[pinIdx], proj.py[pinIdx], 7, t.accent, t.bg, 2)
    if (liveIdx != null && Number.isFinite(proj.px[liveIdx])) dot(ctx, proj.px[liveIdx], proj.py[liveIdx], 6, t.bg, t.text, 2.5)
  }, [proj, pinIdx, liveIdx, width, height, data])

  if (!valid) return <div className="tm-hint" data-testid="track-map">No position channels for this lap.</div>

  const pointerIndex = (e: React.MouseEvent<HTMLCanvasElement>): number | null => {
    if (!proj) return null
    const r = e.currentTarget.getBoundingClientRect()
    return nearestOnScreen(proj.px, proj.py, e.clientX - r.left, e.clientY - r.top)
  }

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const idx = pointerIndex(e)
    setHover((prev) => (prev === idx ? prev : idx))
    setStoreHover(sync, idx == null ? null : data.d[idx], id)
  }

  return (
    <div className="tm-root" data-testid="track-map">
      {title && <div className="tm-title">{title}</div>}
      <div className="tm-wrap" ref={wrapRef} style={{ height }}>
        <canvas
          ref={canvasRef}
          data-testid="track-map-canvas"
          onMouseMove={onMove}
          onMouseLeave={() => {
            setHover(null)
            setStoreHover(sync, null, id)
          }}
          onClick={(e) => {
            const idx = pointerIndex(e)
            if (idx != null) setPinned(sync, data.d[idx])
          }}
        />
        <ReadoutPanel data={data} hover={hover} ext={extIdx} pinned={pinIdx} />
        {data.color && <ColourLegend color={data.color} />}
      </div>
    </div>
  )
}

function cornerAt(data: MapPayload, x: number): string | null {
  for (const s of data.spans) if (x >= s.from && x <= s.to) return s.name
  return null
}

function ReadoutPanel({ data, hover, ext, pinned }: { data: MapPayload; hover: number | null; ext: number | null; pinned: number | null }) {
  let idx = hover ?? ext
  let mode: "hover" | "pinned" = "hover"
  if (idx == null && pinned != null) {
    idx = pinned
    mode = "pinned"
  }
  if (idx == null) return <div className="tm-panel tm-hint">Hover the line for telemetry · click to pin</div>
  const dist = data.d[idx] ?? 0
  const corner = cornerAt(data, dist)
  const hasRef = data.channels.some((c) => c.ref)
  return (
    <div className="tm-panel" data-testid="map-readout">
      <div className="tm-head">
        {corner ? `${corner} · ` : ""}
        {fmt(dist, 0)} m{mode === "pinned" ? " · pinned" : ""}
      </div>
      <table>
        <tbody>
          {hasRef && (
            <tr>
              <th />
              <th>{data.cmp_label || "Lap"}</th>
              <th>{data.ref_label || "Ref"}</th>
              <th>Δ</th>
            </tr>
          )}
          {data.channels.map((ch) => {
            const v = ch.values[idx!]
            const r = ch.ref ? ch.ref[idx!] : null
            const dec = ch.decimals ?? 1
            const d = ch.ref && v != null && r != null ? v - r : null
            return (
              <tr key={ch.label}>
                <td>{ch.unit ? `${ch.label} (${ch.unit})` : ch.label}</td>
                <td className="tm-num" data-channel={ch.label}>
                  {fmt(v, dec)}
                </td>
                {hasRef && <td className="tm-num">{ch.ref ? fmt(r, dec) : ""}</td>}
                {hasRef && <td className="tm-num">{ch.ref ? fmtSigned(d, dec) : ""}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ColourLegend({ color }: { color: NonNullable<MapPayload["color"]> }) {
  const dec = color.decimals ?? 0
  return (
    <div className="tm-legend">
      <div className="tm-bar" style={{ background: scaleGradient(color.scale) }} />
      <div className="tm-bar-labels">
        <span>{fmt(color.min, dec)}</span>
        <span>{color.label}</span>
        <span>{fmt(color.max, dec)}</span>
      </div>
    </div>
  )
}
