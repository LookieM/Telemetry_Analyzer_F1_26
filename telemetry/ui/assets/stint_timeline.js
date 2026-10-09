// Stint bars per strategy / session: segments sized by laps, coloured by compound.

function el(tag, cls, text) {
  const e = document.createElement(tag)
  if (cls) e.className = cls
  if (text != null) e.textContent = text
  return e
}

export default function (component) {
  const { data, parentElement } = component
  const root = parentElement.querySelector(".st-root")
  if (!root || !data) return
  root.textContent = ""
  const total = Math.max(1, data.laps_total || 1)

  for (const row of data.rows || []) {
    const line = el("div", "st-row")
    line.appendChild(el("div", "st-label", row.label || ""))
    const track = el("div", "st-track")
    for (const s of row.stints || []) {
      const laps = Math.max(0, s.to - s.from + 1)
      const seg = el("div", "st-seg")
      seg.style.flexGrow = String(laps)
      seg.style.flexBasis = "0"
      seg.style.background = s.color || "var(--st-gray-color, #888)"
      if (s.light) seg.classList.add("st-light")
      seg.title = s.title || `${s.text || ""} L${s.from}–${s.to} (${laps} laps)`
      seg.appendChild(el("span", "st-text", laps >= total * 0.06 ? `${s.text || ""} ${laps}` : ""))
      track.appendChild(seg)
    }
    line.appendChild(track)
    line.appendChild(el("div", "st-note", row.note || ""))
    root.appendChild(line)
  }

  if (data.show_axis !== false) {
    const axis = el("div", "st-row st-axis-row")
    axis.appendChild(el("div", "st-label", ""))
    const ticks = el("div", "st-track st-axis")
    const step = total > 40 ? 10 : 5
    for (let lap = step; lap < total; lap += step) {
      const t = el("span", "st-tick", String(lap))
      t.style.left = `${(lap / total) * 100}%`
      ticks.appendChild(t)
    }
    axis.appendChild(ticks)
    axis.appendChild(el("div", "st-note", `${total} laps`))
    root.appendChild(axis)
  }
}
