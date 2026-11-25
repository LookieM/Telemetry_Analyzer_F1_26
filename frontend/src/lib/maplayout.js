export const MAP_PAD = 22;
export const HOVER_RADIUS_PX = 36;
export function projectTrack(x, y, outline, w, h, pad = MAP_PAD) {
    const ox0 = outline?.x ?? [];
    const oy0 = outline?.y ?? [];
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    const take = (xs, ys) => {
        for (let i = 0; i < xs.length; i++) {
            const a = xs[i];
            const b = ys[i];
            if (a == null || b == null)
                continue;
            if (a < minX)
                minX = a;
            if (a > maxX)
                maxX = a;
            if (b < minY)
                minY = b;
            if (b > maxY)
                maxY = b;
        }
    };
    take(x, y);
    take(ox0, oy0);
    if (!Number.isFinite(minX))
        return { px: [], py: [], ox: [], oy: [] };
    const k = Math.min((w - 2 * pad) / Math.max(1e-6, maxX - minX), (h - 2 * pad) / Math.max(1e-6, maxY - minY));
    const offX = (w - k * (maxX - minX)) / 2;
    const offY = (h - k * (maxY - minY)) / 2;
    const sx = (v) => offX + (v - minX) * k;
    const sy = (v) => offY + (maxY - v) * k; // world Y up, canvas Y down
    return {
        px: x.map((v) => (v == null ? NaN : sx(v))),
        py: y.map((v) => (v == null ? NaN : sy(v))),
        ox: ox0.map(sx),
        oy: oy0.map(sy),
    };
}
/** Index of the projected point nearest to (mx, my) within `radius` pixels, else null. */
export function nearestOnScreen(px, py, mx, my, radius = HOVER_RADIUS_PX) {
    let best = -1;
    let bestD = Infinity;
    for (let i = 0; i < px.length; i++) {
        const dx = px[i] - mx;
        const dy = py[i] - my;
        const dd = dx * dx + dy * dy;
        if (dd < bestD) {
            bestD = dd;
            best = i;
        }
    }
    return best >= 0 && bestD <= radius * radius ? best : null;
}
/** The part of a map payload inside a distance window (the outline is dropped so the view fits the window). */
export function zoomMapPayload(data, range) {
    const idx = [];
    data.d.forEach((v, i) => {
        if (v != null && v >= range[0] && v <= range[1])
            idx.push(i);
    });
    if (idx.length < 2)
        return data;
    const pick = (a) => idx.map((i) => a[i]);
    return {
        ...data,
        x: pick(data.x),
        y: pick(data.y),
        d: pick(data.d),
        color: data.color && { ...data.color, values: pick(data.color.values) },
        channels: data.channels.map((c) => ({ ...c, values: pick(c.values), ref: c.ref && pick(c.ref) })),
        labels: data.labels.filter((l) => l.d >= range[0] && l.d <= range[1]),
        spans: data.spans.filter((s) => s.to >= range[0] && s.from <= range[1]),
        outline: null,
    };
}
