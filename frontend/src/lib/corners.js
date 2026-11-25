import { BRAKE, NEUTRAL, THROTTLE } from "./colors";
/** A corner time difference below this (s) is noise: neither a loss nor a gain. */
export const NOISE_S = 0.03;
/** Metres of track kept around a corner when the map and traces zoom to it. */
export const ZOOM_MARGIN_M = 60;
export function buildCornerRows(p) {
    return p.corners.map((c, i) => ({
        id: c.id,
        order: i + 1,
        name: c.name,
        speedClass: c.speed_class,
        startM: c.start_m,
        endM: c.end_m,
        apexM: c.apex_m,
        complex: c.merged_from.length > 1,
        time: c.focus.time_s,
        timeDelta: c.delta.time_s,
        entry: c.focus.entry_kmh,
        entryDelta: c.delta.entry_kmh,
        vmin: c.focus.vmin_kmh,
        vminDelta: c.delta.vmin_kmh,
        exit: c.focus.exit_kmh,
        exitDelta: c.delta.exit_kmh,
        brake: c.focus.brake_m,
        brakeDelta: c.delta.brake_m,
        trail: c.focus.trail_m,
        trailDelta: c.delta.trail_m,
        throttle: c.focus.throttle_m,
        throttleDelta: c.delta.throttle_m,
        callouts: c.callouts,
        points: { brake: c.focus.brake_m, throttle: c.focus.throttle_m, refBrake: c.ref.brake_m, refThrottle: c.ref.throttle_m },
    }));
}
/** Sorted copy; corners without a value for the key go last in either direction. */
export function sortRows(rows, key, dir) {
    const sign = dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
        const x = a[key];
        const y = b[key];
        if (x == null && y == null)
            return a.order - b.order;
        if (x == null)
            return 1;
        if (y == null)
            return -1;
        return x === y ? a.order - b.order : sign * (x - y);
    });
}
/** Distance window to zoom to: the corner plus a margin on both sides, kept inside [0, trackLength]. */
export function zoomRange(c, trackLength, margin = ZOOM_MARGIN_M) {
    const from = Math.max(0, c.startM - margin);
    const to = c.endM + margin;
    return [from, trackLength != null ? Math.min(trackLength, to) : to];
}
/** Colour class of a corner time difference (positive = slower than the reference). */
export function lossKind(delta, threshold = NOISE_S) {
    if (delta == null || Math.abs(delta) < threshold)
        return "flat";
    return delta > 0 ? "loss" : "gain";
}
/** Brake-point and full-throttle markers of a corner: focus lap in colour, reference lap grey. */
export function cornerMarkers(row) {
    const out = [];
    const add = (x, label, color) => {
        if (x != null)
            out.push({ x, label, color });
    };
    add(row.points.brake, "Brake", BRAKE);
    add(row.points.throttle, "Full throttle", THROTTLE);
    add(row.points.refBrake, "Brake (ref)", NEUTRAL);
    add(row.points.refThrottle, "Full thr (ref)", NEUTRAL);
    return out;
}
/** The corner with the biggest time loss above the noise, or null. */
export function biggestLoss(rows) {
    let best = null;
    for (const r of rows)
        if (r.timeDelta != null && r.timeDelta >= NOISE_S && (!best || r.timeDelta > (best.timeDelta ?? 0)))
            best = r;
    return best;
}
/** Name of the corner a distance falls in, or null on a straight. */
export function cornerAt(rows, x) {
    if (x == null)
        return null;
    return rows.find((r) => x >= r.startM && x <= r.endM)?.name ?? null;
}
