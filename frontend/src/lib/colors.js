/** Colour scales for the map (same maths as track_map.js) and the theme-independent palette. */
export function hexToRgb(hex) {
    const h = hex.replace("#", "");
    const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
    const n = parseInt(full, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
/** Colour at position t (0..1) on a piecewise-linear scale; null when t is not finite. */
export function scaleColor(scale, t) {
    if (!Number.isFinite(t) || scale.length === 0)
        return null;
    const x = Math.min(1, Math.max(0, t));
    for (let i = 1; i < scale.length; i++) {
        const [t1, c1] = scale[i];
        const [t0, c0] = scale[i - 1];
        if (x <= t1) {
            const f = t1 > t0 ? (x - t0) / (t1 - t0) : 0;
            const a = hexToRgb(c0);
            const b = hexToRgb(c1);
            return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",")})`;
        }
    }
    return scale[scale.length - 1][1];
}
/** CSS linear-gradient for a legend bar. */
export function scaleGradient(scale) {
    return `linear-gradient(90deg, ${scale.map(([t, c]) => `${c} ${t * 100}%`).join(", ")})`;
}
// Trace colours (telemetry/ui/palette.py).
export const FOCUS = "#E03C31";
export const REF = "#3E7CC9";
export const THROTTLE = "#2E9E44";
export const BRAKE = "#D7263D";
export const GEAR = "#8A6FD1";
export const NEUTRAL = "#8A9099";
export const DELTA = "#E8A317";
/** Wheel order in the data (exports are front-first): 0=FL, 1=FR, 2=RL, 3=RR. */
export const WHEELS = ["FL", "FR", "RL", "RR"];
export const WHEEL_COLORS = { RL: "#2E9E44", RR: "#D7263D", FL: "#3E7CC9", FR: "#E8A317" };
/** Car layout (front row first). */
export const CAR_LAYOUT = ["FL", "FR", "RL", "RR"];
/** Plan colours on the race trace. */
export const PLAN_COLORS = ["#E03C31", "#3E7CC9", "#2E9E44", "#E8A317", "#8A6FD1"];
export const TEMP_COLD = "#3E7CC9";
export const TEMP_OK = "#2E9E44";
export const TEMP_HOT = "#D7263D";
export function tempColor(t, lo, hi) {
    if (typeof t !== "number" || !Number.isFinite(t))
        return NEUTRAL;
    if (t < lo)
        return TEMP_COLD;
    if (t > hi)
        return TEMP_HOT;
    return TEMP_OK;
}
