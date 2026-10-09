// Stacked uPlot panes with a shared cursor and shared x zoom (MoTeC-style trace view).
// Loaded after uPlot.iife.min.js in the same module, so `uPlot` is in scope.
// Streamlit calls the default export again whenever `data` changes; plots are rebuilt only
// when the data signature changes, so zoom survives cursor clicks and other reruns.

const STATE = new WeakMap()
// Cursor bus shared with the track map component (a separate module): charts publish
// kind "chart", maps publish kind "map"; each side only reacts to the other kind.
const CURSOR_EVENT = "telemetria:cursor"
// Set while a map event drives the cursor, so synced panes do not echo it back.
let APPLYING_EXTERNAL = false

function cssVar(el, name, fallback) {
  const v = getComputedStyle(el).getPropertyValue(name).trim()
  return v || fallback
}

function readTheme(el) {
  return {
    text: cssVar(el, "--st-text-color", "#1a1a1a"),
    grid: cssVar(el, "--st-border-color-light", "rgba(128,128,128,0.18)"),
    border: cssVar(el, "--st-border-color", "rgba(128,128,128,0.45)"),
    band: cssVar(el, "--st-secondary-background-color", "rgba(128,128,128,0.10)"),
    primary: cssVar(el, "--st-primary-color", "#ff4b4b"),
    font: cssVar(el, "--st-font", "sans-serif"),
  }
}

function fmt(v, decimals) {
  return v == null || !Number.isFinite(v) ? "—" : v.toFixed(decimals)
}

function drawBands(u, st, labels) {
  const bands = st.data.bands || []
  if (!bands.length) return
  const ctx = u.ctx
  const { top, height } = u.bbox
  const dpr = devicePixelRatio || 1
  ctx.save()
  bands.forEach((b, i) => {
    const x0 = u.valToPos(b.from, "x", true)
    const x1 = u.valToPos(b.to, "x", true)
    if (x1 < u.bbox.left || x0 > u.bbox.left + u.bbox.width) return
    ctx.globalAlpha = b.color ? 0.14 : i % 2 ? 0.0 : 0.55
    ctx.fillStyle = b.color || st.theme.band
    ctx.fillRect(x0, top, x1 - x0, height)
    if (labels && b.label && x1 - x0 > 18 * dpr) {
      ctx.globalAlpha = 0.75
      ctx.fillStyle = st.theme.text
      ctx.font = `${10 * dpr}px ${st.theme.font}`
      ctx.fillText(b.label, x0 + 3 * dpr, top + 11 * dpr)
    }
  })
  ctx.restore()
}

function vline(u, x, color, dash, width) {
  const px = u.valToPos(x, "x", true)
  if (!Number.isFinite(px) || px < u.bbox.left || px > u.bbox.left + u.bbox.width) return null
  const ctx = u.ctx
  ctx.save()
  ctx.strokeStyle = color
  ctx.lineWidth = width * (devicePixelRatio || 1)
  ctx.setLineDash(dash)
  ctx.beginPath()
  ctx.moveTo(px, u.bbox.top)
  ctx.lineTo(px, u.bbox.top + u.bbox.height)
  ctx.stroke()
  ctx.restore()
  return px
}

function drawOverlay(u, st, labels) {
  const dpr = devicePixelRatio || 1
  for (const m of st.data.markers || []) {
    const px = vline(u, m.x, m.color || st.theme.border, [4 * dpr, 3 * dpr], 1)
    if (px != null && labels && m.label) {
      const ctx = u.ctx
      ctx.save()
      ctx.fillStyle = m.color || st.theme.text
      ctx.font = `${10 * dpr}px ${st.theme.font}`
      ctx.fillText(m.label, px + 3 * dpr, u.bbox.top + u.bbox.height - 4 * dpr)
      ctx.restore()
    }
  }
  if (st.pinned != null) vline(u, st.pinned, st.theme.primary, [], 1.5)
}

function seriesOpts(s, paneDecimals, theme) {
  const o = {
    label: s.label,
    stroke: s.color || theme.text,
    width: s.width ?? 1.5,
    spanGaps: false,
    value: (u, v) => fmt(v, s.decimals ?? paneDecimals),
    points: { show: false },
  }
  if (s.dash) o.dash = [6, 4]
  if (s.mode === "points") {
    o.paths = () => null
    const c = s.color || theme.text
    o.points = { show: true, size: s.size ?? 6, fill: s.hollow ? "rgba(0,0,0,0)" : c, stroke: c, width: s.hollow ? 1.5 : 1 }
  } else if (s.mode === "step") {
    o.paths = uPlot.paths.stepped({ align: 1 })
  }
  return o
}

function build(parentElement, data, setTriggerValue) {
  const host = parentElement.querySelector(".tc-root")
  const theme = readTheme(host)
  const st = { data, theme, plots: [], pinned: data.cursor_x ?? null, sig: data.sig, syncing: false, down: null }
  host.textContent = ""
  if (!data.x || !data.x.length || !data.panes || !data.panes.length) {
    const empty = document.createElement("div")
    empty.className = "tc-empty"
    empty.textContent = data.empty_text || "No data for this chart."
    host.appendChild(empty)
    return st
  }

  const width = Math.max(320, host.clientWidth || 900)
  const syncKey = data.sync || "lap"
  const last = data.panes.length - 1
  const axisFont = `11px ${theme.font}`

  data.panes.forEach((pane, i) => {
    const wrap = document.createElement("div")
    wrap.className = "tc-pane"
    const head = document.createElement("div")
    head.className = "tc-head"
    head.textContent = pane.unit ? `${pane.title} · ${pane.unit}` : pane.title
    wrap.appendChild(head)
    host.appendChild(wrap)

    const dec = pane.decimals ?? 1
    const isLast = i === last
    const opts = {
      width,
      height: pane.height || 150,
      padding: [6, 10, 0, 0],
      scales: { x: { time: false }, y: pane.range ? { range: pane.range } : {} },
      series: [
        { label: data.x_label || "x", value: (u, v) => fmt(v, data.x_decimals ?? 0) },
        ...pane.series.map((s) => seriesOpts(s, dec, theme)),
      ],
      axes: [
        {
          stroke: theme.text,
          font: axisFont,
          grid: { stroke: theme.grid, width: 1 },
          ticks: { stroke: theme.grid, width: 1, size: 4 },
          size: isLast ? 30 : 8,
          values: isLast ? undefined : (u, vals) => vals.map(() => ""),
        },
        {
          stroke: theme.text,
          font: axisFont,
          grid: { stroke: theme.grid, width: 1 },
          ticks: { stroke: theme.grid, width: 1, size: 4 },
          size: 58,
          values: (u, vals) => vals.map((v) => fmt(v, pane.axis_decimals ?? 0)),
        },
      ],
      cursor: {
        sync: { key: syncKey, setSeries: false },
        drag: { x: true, y: false, setScale: true, dist: 5 },
        points: { size: 6 },
      },
      legend: { show: true, live: true },
      hooks: {
        drawClear: [(u) => drawBands(u, st, i === 0)],
        draw: [(u) => drawOverlay(u, st, i === 0)],
        setCursor: [
          (u) => {
            if (i !== 0 || APPLYING_EXTERNAL) return
            const left = u.cursor.left
            const x = left != null && left >= 0 ? u.posToVal(left, "x") : null
            window.dispatchEvent(new CustomEvent(CURSOR_EVENT, { detail: { kind: "chart", sync: syncKey, x } }))
          },
        ],
        setScale: [
          (u, key) => {
            if (key !== "x" || st.syncing) return
            st.syncing = true
            const { min, max } = u.scales.x
            for (const p of st.plots) {
              if (p !== u && (p.scales.x.min !== min || p.scales.x.max !== max)) p.setScale("x", { min, max })
            }
            st.syncing = false
          },
        ],
      },
    }
    const payload = [data.x, ...pane.series.map((s) => s.values)]
    const u = new uPlot(opts, payload, wrap)
    u.over.addEventListener("mousedown", (e) => {
      st.down = e.clientX
    })
    u.over.addEventListener("mouseup", (e) => {
      if (st.down != null && Math.abs(e.clientX - st.down) < 4 && u.cursor.left != null && u.cursor.left >= 0) {
        const v = u.posToVal(u.cursor.left, "x")
        if (Number.isFinite(v)) {
          st.pinned = v
          st.plots.forEach((p) => p.redraw(false))
          setTriggerValue("clicked_x", v)
        }
      }
      st.down = null
    })
    st.plots.push(u)
  })

  st.observer = new ResizeObserver(() => {
    const w = Math.max(320, host.clientWidth)
    for (const p of st.plots) if (Math.abs(p.width - w) > 1) p.setSize({ width: w, height: p.height })
  })
  st.observer.observe(host)

  st.onBus = (e) => {
    const d = e.detail || {}
    if (d.kind !== "map" || d.sync !== syncKey || !st.plots.length) return
    // A programmatic setCursor is not re-published through uPlot sync, so move every pane.
    APPLYING_EXTERNAL = true
    try {
      for (const u of st.plots) {
        if (d.x == null) u.setCursor({ left: -10, top: -10 })
        else u.setCursor({ left: u.valToPos(d.x, "x"), top: Math.max(1, u.bbox.height / (2 * (devicePixelRatio || 1))) })
      }
    } finally {
      APPLYING_EXTERNAL = false
    }
  }
  window.addEventListener(CURSOR_EVENT, st.onBus)
  return st
}

function destroy(st) {
  if (!st) return
  st.observer?.disconnect()
  if (st.onBus) window.removeEventListener(CURSOR_EVENT, st.onBus)
  st.plots.forEach((p) => p.destroy())
  st.plots = []
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  if (!data) return
  let st = STATE.get(parentElement)
  const themeNow = readTheme(parentElement.querySelector(".tc-root"))
  const themeChanged = st && JSON.stringify(themeNow) !== JSON.stringify(st.theme)
  if (st && st.sig === data.sig && !themeChanged) {
    st.data = data
    const next = data.cursor_x ?? null
    if (next !== st.pinned) {
      st.pinned = next
      st.plots.forEach((p) => p.redraw(false))
    }
  } else {
    destroy(st)
    st = build(parentElement, data, setTriggerValue)
    STATE.set(parentElement, st)
  }
  return () => {
    destroy(STATE.get(parentElement))
    STATE.delete(parentElement)
  }
}
