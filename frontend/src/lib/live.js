/** Live view: message types, delta trace buffer and the WebSocket hook. */
import { useEffect, useRef, useState } from "react";
export const ERS_MODES = ["None", "Medium", "Hotlap", "Overtake"];
const COMPOUND_COLORS = { 22: "#B5179E", 16: "#D7263D", 17: "#E8A317", 18: "#C9CED6", 19: "#8A9099", 20: "#5C6670", 21: "#3A4148", 7: "#2E9E44", 8: "#1F6FD1" };
export const compoundColor = (code) => (code != null ? COMPOUND_COLORS[code] ?? "#8A9099" : "#8A9099");
/** Delta-vs-distance points of the current lap; resets when the lap distance wraps. */
export function pushDelta(points, dist, delta, maxPoints = 1500) {
    if (delta == null || !Number.isFinite(delta))
        return points;
    const last = points[points.length - 1];
    const next = last && dist < last[0] - 200 ? [] : points.slice();
    if (next.length && dist <= next[next.length - 1][0])
        return next;
    next.push([dist, delta]);
    return next.length > maxPoints ? next.slice(next.length - maxPoints) : next;
}
/** Signed gap to a rival: negative = ahead. */
export function gapLabel(gap) {
    if (gap == null || !Number.isFinite(gap))
        return "—";
    if (Math.abs(gap) < 0.05)
        return "0.0";
    return `${gap > 0 ? "+" : "−"}${Math.abs(gap).toFixed(1)}`;
}
/** Which optional cards the Live page shows. A running engineer program or duel is never hidden, whatever the session. */
export function liveSections(sessionType, engineerActive, duelActive) {
    const t = sessionType.toLowerCase();
    const race = t === "race";
    const quali = t.includes("quali");
    const running = engineerActive || duelActive;
    return { strategy: race, engineer: running || (!race && !quali) };
}
export function useLive() {
    const [data, setData] = useState({ snapshot: null, status: null, events: [], deltaTrace: [], lastTrace: [], socket: "connecting", lastAt: 0 });
    const trace = useRef([]);
    const traceLast = useRef([]);
    useEffect(() => {
        let ws = null;
        let timer;
        let stopped = false;
        const connect = () => {
            const proto = location.protocol === "https:" ? "wss" : "ws";
            ws = new WebSocket(`${proto}://${location.host}/ws/live`);
            ws.onopen = () => setData((d) => ({ ...d, socket: "open" }));
            ws.onclose = () => {
                setData((d) => ({ ...d, socket: "closed" }));
                if (!stopped)
                    timer = window.setTimeout(connect, 1500);
            };
            ws.onmessage = (ev) => {
                let m;
                try {
                    m = JSON.parse(ev.data);
                }
                catch {
                    return;
                }
                if (m.type === "snapshot") {
                    const s = m;
                    trace.current = pushDelta(trace.current, s.timing.lap_distance, s.timing.delta_best);
                    traceLast.current = pushDelta(traceLast.current, s.timing.lap_distance, s.timing.delta_last);
                    setData((d) => ({ ...d, snapshot: s, deltaTrace: trace.current, lastTrace: traceLast.current, lastAt: Date.now() }));
                }
                else if (m.type === "status") {
                    setData((d) => ({ ...d, status: m }));
                }
                else if (m.type === "event") {
                    setData((d) => ({ ...d, events: [m, ...d.events].slice(0, 4) }));
                }
            };
        };
        connect();
        return () => {
            stopped = true;
            window.clearTimeout(timer);
            if (ws) {
                ws.onopen = ws.onclose = ws.onmessage = null;
                ws.close();
            }
        };
    }, []);
    return data;
}
