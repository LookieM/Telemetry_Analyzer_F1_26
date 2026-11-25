export const GG_CHANNELS = ["speed"];
export const GG_EXTRAS = ["g_lat", "g_long"];
export const SPEED_SCALE = [
    [0, "#3E7CC9"],
    [0.5, "#E8A317"],
    [1, "#E03C31"],
];
export function buildGG(p) {
    const lat = p?.channels.g_lat;
    const long = p?.channels.g_long;
    if (!p || !lat || !long)
        return null;
    const speed = p.channels.speed ?? [];
    const points = [];
    for (let i = 0; i < p.x.length; i++) {
        const a = lat[i];
        const b = long[i];
        if (a == null || b == null || !Number.isFinite(a) || !Number.isFinite(b))
            continue;
        points.push({ x: p.x[i], lat: a, long: b, speed: speed[i] ?? null });
    }
    if (!points.length)
        return null;
    let maxAbs = 0;
    let latPeak = 0;
    let brake = 0;
    let accel = 0;
    let sMin = Infinity;
    let sMax = -Infinity;
    for (const pt of points) {
        maxAbs = Math.max(maxAbs, Math.abs(pt.lat), Math.abs(pt.long));
        latPeak = Math.max(latPeak, Math.abs(pt.lat));
        brake = Math.max(brake, -pt.long);
        accel = Math.max(accel, pt.long);
        if (pt.speed != null) {
            sMin = Math.min(sMin, pt.speed);
            sMax = Math.max(sMax, pt.speed);
        }
    }
    return {
        points,
        limit: Math.max(1, Math.ceil(maxAbs * 2) / 2),
        speedMin: Number.isFinite(sMin) ? sMin : 0,
        speedMax: Number.isFinite(sMax) ? sMax : 0,
        peaks: { lat: latPeak, brake, accel },
    };
}
/** Index of the point nearest to a lap distance (points are in distance order), or -1. */
export function nearestPoint(points, x) {
    if (x == null || !points.length)
        return -1;
    let lo = 0;
    let hi = points.length - 1;
    while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (points[mid].x < x)
            lo = mid + 1;
        else
            hi = mid;
    }
    if (lo > 0 && Math.abs(points[lo - 1].x - x) <= Math.abs(points[lo].x - x))
        return lo - 1;
    return lo;
}
