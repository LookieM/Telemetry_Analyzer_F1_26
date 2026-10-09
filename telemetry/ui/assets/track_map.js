// Track map on canvas: live channel readout under the mouse, click to pin the lap cursor,
// and a cursor shared with the uPlot trace charts through a window event bus.

const STATE = new WeakMap()
const CURSOR_EVENT = "telemetria:cursor"
const PAD = 22
const HOVER_RADIUS_PX = 36

function cssVar(el, name, fallback) {
  const v = getComputedStyle(el).getPropertyValue(name).trim()
  return v || fallback
}

function readTheme(el) {
  return {
    text: cssVar(el, "--st-text-color", "#1a1a1a"),
    bg: cssVar(el, "--st-background-color", "#ffffff"),
    border: cssVar(el, "--st-border-color", "rgba(128,128,128,0.45)"),
    primary: cssVar(el, "--st-primary-color", "#ff4b4b"),
    font: cssVar(el, "--st-font", "sans-serif"),
  }
}

function hexToRgb(hex) {
  const h = hex.replace("#", "")
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function scaleColor(scale, t) {
  if (!Number.isFinite(t)) return null
  t = Math.min(1, Math.max(0, t))
  for (let i = 1; i < scale.length; i++) {
    const [t1, c1] = scale[i]
    const [t0, c0] = scale[i - 1]
    if (t <= t1) {
      const f = t1 > t0 ? (t - t0) / (t1 - t0) : 0
      const a = hexToRgb(c0)
      const b = hexToRgb(c1)
      return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",")})`
    }
  }
  return scale[scale.length - 1][1]
}

function fmt(v, decimals) {
  return v == null || !Number.isFinite(v) ? "—" : v.toFixed(decimals)
}

function nearestByDistance(d, x) {
  // d is ascending lap distance
  let lo = 0
  let hi = d.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (d[mid] < x) lo = mid
    else hi = mid
  }
  return Math.abs(d[lo] - x) <= Math.abs(d[hi] - x) ? lo : hi
}

function layout(st) {
  const { data, canvas, wrap } = st
  const dpr = devicePixelRatio || 1
  const w = Math.max(280, wrap.clientWidth)
  const h = data.height || 520
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  const xs = data.x.concat((data.outline && data.outline.x) || [])
  const ys = data.y.concat((data.outline && data.outline.y) || [])
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (let i = 0; i < xs.length; i++) {
    if (xs[i] == null || ys[i] == null) continue
    minX = Math.min(minX, xs[i]); maxX = Math.max(maxX, xs[i])
    minY = Math.min(minY, ys[i]); maxY = Math.max(maxY, ys[i])
  }
  const k = Math.min((w - 2 * PAD) / Math.max(1e-6, maxX - minX), (h - 2 * PAD) / Math.max(1e-6, maxY - minY))
  const ox = (w - k * (maxX - minX)) / 2
  const oy = (h - k * (maxY - minY)) / 2
  const sx = (v) => ox + (v - minX) * k
  const sy = (v) => oy + (maxY - v) * k // world Y up, canvas Y down
  st.w = w
  st.h = h
  st.px = data.x.map((v) => (v == null ? NaN : sx(v)))
  st.py = data.y.map((v) => (v == null ? NaN : sy(v)))
  st.ox = ((data.outline && data.outline.x) || []).map(sx)
  st.oy = ((data.outline && data.outline.y) || []).map(sy)
}

function dot(ctx, x, y, r, fill, stroke, lw) {
  ctx.beginPath()
  ctx.arc(x, y, r, 0, Math.PI * 2)
  ctx.fillStyle = fill
  ctx.fill()
  ctx.lineWidth = lw
  ctx.strokeStyle = stroke
  ctx.stroke()
}

function draw(st) {
  const { data, canvas, theme } = st
  const dpr = devicePixelRatio || 1
  const ctx = canvas.getContext("2d")
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, st.w, st.h)
  ctx.lineJoin = "round"
  ctx.lineCap = "round"

  if (st.ox.length > 1) {
    ctx.save()
    ctx.globalAlpha = 0.28
    ctx.strokeStyle = theme.border
    ctx.lineWidth = 11
    ctx.beginPath()
    st.ox.forEach((x, i) => (i ? ctx.lineTo(x, st.oy[i]) : ctx.moveTo(x, st.oy[i])))
    ctx.stroke()
    ctx.restore()
  }

  const c = data.color
  const lo = c ? c.min : 0
  const hi = c ? c.max : 1
  ctx.lineWidth = 3.5
  for (let i = 1; i < st.px.length; i++) {
    if (!Number.isFinite(st.px[i]) || !Number.isFinite(st.px[i - 1])) continue
    const v = c ? c.values[i] : null
    ctx.strokeStyle = (v != null && scaleColor(c.scale, (v - lo) / Math.max(1e-9, hi - lo))) || theme.text
    ctx.beginPath()
    ctx.moveTo(st.px[i - 1], st.py[i - 1])
    ctx.lineTo(st.px[i], st.py[i])
    ctx.stroke()
  }

  ctx.font = `600 10px ${theme.font}`
  ctx.fillStyle = theme.text
  ctx.globalAlpha = 0.8
  for (const lab of data.labels || []) {
    const i = nearestByDistance(data.d, lab.d)
    if (Number.isFinite(st.px[i])) ctx.fillText(lab.text, st.px[i] + 7, st.py[i] - 6)
  }
  ctx.globalAlpha = 1

  if (st.pinned != null) {
    const i = nearestByDistance(data.d, st.pinned)
    dot(ctx, st.px[i], st.py[i], 7, theme.primary, theme.bg, 2)
  }
  const live = st.hover ?? (st.ext != null ? nearestByDistance(data.d, st.ext) : null)
  if (live != null) dot(ctx, st.px[live], st.py[live], 6, theme.bg, theme.text, 2.5)
}

function cornerAt(data, x) {
  for (const s of data.spans || []) if (x >= s.from && x <= s.to) return s.name
  return null
}

function renderPanel(st) {
  const { data, panel } = st
  let idx = st.hover
  let mode = "hover"
  if (idx == null && st.ext != null) idx = nearestByDistance(data.d, st.ext)
  if (idx == null && st.pinned != null) {
    idx = nearestByDistance(data.d, st.pinned)
    mode = "pinned"
  }
  panel.textContent = ""
  if (idx == null) {
    const hint = document.createElement("div")
    hint.className = "tm-hint"
    hint.textContent = "Hover the line for telemetry · click to pin"
    panel.appendChild(hint)
    return
  }
  const dist = data.d[idx]
  const head = document.createElement("div")
  head.className = "tm-head"
  const corner = cornerAt(data, dist)
  head.textContent = `${corner ? corner + " · " : ""}${fmt(dist, 0)} m${mode === "pinned" ? " · pinned" : ""}`
  panel.appendChild(head)

  const hasRef = (data.channels || []).some((ch) => ch.ref)
  const table = document.createElement("table")
  if (hasRef) {
    const tr = document.createElement("tr")
    for (const t of ["", data.cmp_label || "Lap", data.ref_label || "Ref", "Δ"]) {
      const th = document.createElement("th")
      th.textContent = t
      tr.appendChild(th)
    }
    table.appendChild(tr)
  }
  for (const ch of data.channels || []) {
    const tr = document.createElement("tr")
    const v = ch.values[idx]
    const cells = [ch.unit ? `${ch.label} (${ch.unit})` : ch.label, fmt(v, ch.decimals ?? 1)]
    if (hasRef) {
      const r = ch.ref ? ch.ref[idx] : null
      cells.push(ch.ref ? fmt(r, ch.decimals ?? 1) : "")
      const dlt = ch.ref && v != null && r != null ? v - r : null
      cells.push(ch.ref ? (dlt == null ? "—" : (dlt > 0 ? "+" : "") + dlt.toFixed(ch.decimals ?? 1)) : "")
    }
    cells.forEach((text, k) => {
      const td = document.createElement("td")
      td.textContent = text
      if (k > 0) td.className = "tm-num"
      tr.appendChild(td)
    })
    table.appendChild(tr)
  }
  panel.appendChild(table)
}

function renderLegend(st) {
  const { data, legend } = st
  legend.textContent = ""
  const c = data.color
  if (!c) return
  const bar = document.createElement("div")
  bar.className = "tm-bar"
  bar.style.background = `linear-gradient(90deg, ${c.scale.map(([t, col]) => `${col} ${t * 100}%`).join(", ")})`
  const lab = document.createElement("div")
  lab.className = "tm-bar-labels"
  lab.innerHTML = ""
  for (const text of [fmt(c.min, c.decimals ?? 0), c.label, fmt(c.max, c.decimals ?? 0)]) {
    const s = document.createElement("span")
    s.textContent = text
    lab.appendChild(s)
  }
  legend.appendChild(bar)
  legend.appendChild(lab)
}

function nearestOnScreen(st, mx, my) {
  let best = -1
  let bestD = Infinity
  for (let i = 0; i < st.px.length; i++) {
    const dx = st.px[i] - mx
    const dy = st.py[i] - my
    const dd = dx * dx + dy * dy
    if (dd < bestD) {
      bestD = dd
      best = i
    }
  }
  return best >= 0 && bestD <= HOVER_RADIUS_PX * HOVER_RADIUS_PX ? best : null
}

function publish(st, x) {
  window.dispatchEvent(new CustomEvent(CURSOR_EVENT, { detail: { kind: "map", sync: st.data.sync || "lap", x } }))
}

function build(parentElement, data, setTriggerValue) {
  const root = parentElement.querySelector(".tm-root")
  root.textContent = ""
  const st = { data, sig: data.sig, theme: readTheme(root), pinned: data.pinned_d ?? null, hover: null, ext: null }
  if (!data.x || data.x.length < 2) {
    const empty = document.createElement("div")
    empty.className = "tm-hint"
    empty.textContent = data.empty_text || "No position channels for this lap."
    root.appendChild(empty)
    return st
  }
  if (data.title) {
    const title = document.createElement("div")
    title.className = "tm-title"
    title.textContent = data.title
    root.appendChild(title)
  }
  st.wrap = document.createElement("div")
  st.wrap.className = "tm-wrap"
  st.canvas = document.createElement("canvas")
  st.panel = document.createElement("div")
  st.panel.className = "tm-panel"
  st.legend = document.createElement("div")
  st.legend.className = "tm-legend"
  st.wrap.append(st.canvas, st.panel, st.legend)
  root.appendChild(st.wrap)

  layout(st)
  draw(st)
  renderPanel(st)
  renderLegend(st)

  st.canvas.addEventListener("mousemove", (e) => {
    const r = st.canvas.getBoundingClientRect()
    const idx = nearestOnScreen(st, e.clientX - r.left, e.clientY - r.top)
    if (idx === st.hover) return
    st.hover = idx
    draw(st)
    renderPanel(st)
    publish(st, idx == null ? null : st.data.d[idx])
  })
  st.canvas.addEventListener("mouseleave", () => {
    st.hover = null
    draw(st)
    renderPanel(st)
    publish(st, null)
  })
  st.canvas.addEventListener("click", (e) => {
    const r = st.canvas.getBoundingClientRect()
    const idx = nearestOnScreen(st, e.clientX - r.left, e.clientY - r.top)
    if (idx == null) return
    st.pinned = st.data.d[idx]
    draw(st)
    setTriggerValue("clicked_d", st.pinned)
  })

  st.onBus = (e) => {
    const d = e.detail || {}
    if (d.kind !== "chart" || d.sync !== (st.data.sync || "lap") || st.hover != null) return
    st.ext = d.x
    draw(st)
    renderPanel(st)
  }
  window.addEventListener(CURSOR_EVENT, st.onBus)

  st.observer = new ResizeObserver(() => {
    if (Math.abs(st.wrap.clientWidth - st.w) > 1) {
      layout(st)
      draw(st)
    }
  })
  st.observer.observe(st.wrap)
  return st
}

function destroy(st) {
  if (!st) return
  st.observer?.disconnect()
  if (st.onBus) window.removeEventListener(CURSOR_EVENT, st.onBus)
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  if (!data) return
  let st = STATE.get(parentElement)
  if (st && st.sig === data.sig && st.canvas) {
    st.data = data
    const next = data.pinned_d ?? null
    if (next !== st.pinned) {
      st.pinned = next
      draw(st)
      renderPanel(st)
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
