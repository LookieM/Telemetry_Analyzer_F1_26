import { describe, expect, it } from "vitest";
import { buildGG, nearestPoint } from "./gg";
import { sessionPaceTrace } from "./traces";
const payload = (lat, long, speed) => ({
    session_id: 1,
    lap: 3,
    x: lat.map((_, i) => i * 10),
    x_label: "Distance (m)",
    channels: { g_lat: lat, g_long: long, ...(speed ? { speed } : {}) },
    units: {},
});
describe("buildGG", () => {
    it("drops gaps, finds peaks and a half-g axis limit", () => {
        const gg = buildGG(payload([0.2, null, -3.4, 1.1], [-4.6, 0.3, 0.1, 1.2], [300, 250, 120, 200]));
        expect(gg.points.map((p) => p.x)).toEqual([0, 20, 30]);
        expect(gg.limit).toBe(5);
        expect(gg.peaks).toEqual({ lat: 3.4, brake: 4.6, accel: 1.2 });
        expect([gg.speedMin, gg.speedMax]).toEqual([120, 300]);
    });
    it("is null without g channels and keeps at least 1 g of axis", () => {
        expect(buildGG(undefined)).toBeNull();
        expect(buildGG({ ...payload([0.1], [0.1]), channels: { speed: [100] } })).toBeNull();
        expect(buildGG(payload([0.1], [-0.2])).limit).toBe(1);
    });
});
describe("nearestPoint", () => {
    const pts = [0, 10, 20, 30].map((x) => ({ x, lat: 0, long: 0, speed: null }));
    it("finds the closest distance, -1 without a cursor", () => {
        expect(nearestPoint(pts, 14)).toBe(1);
        expect(nearestPoint(pts, 16)).toBe(2);
        expect(nearestPoint(pts, 99)).toBe(3);
        expect(nearestPoint(pts, -5)).toBe(0);
        expect(nearestPoint(pts, null)).toBe(-1);
    });
});
describe("sessionPaceTrace", () => {
    const lap = (n, t, cls, extra = {}) => ({
        lap: n,
        lap_time: t,
        lap_class: cls,
        pit_stop: false,
        delta_best: 0,
        is_best: false,
        ...extra,
    });
    it("splits best / push / other laps and marks pit laps", () => {
        const d = sessionPaceTrace([lap(1, 101, "out"), lap(2, 90.5, "push"), lap(3, 90.1, "push", { is_best: true, fuel_used: 1.6 }), lap(4, 112, "in", { pit_stop: true })]);
        const [best, push, other] = d.panes[0].series;
        expect(best.values).toEqual([null, null, 90.1, null]);
        expect(push.values).toEqual([null, 90.5, null, null]);
        expect(other.values).toEqual([101, null, null, 112]);
        expect(d.panes[0].range[0]).toBeCloseTo(89.6);
        expect(d.panes.map((p) => p.title)).toEqual(["Lap time", "Fuel used"]);
        expect(d.markers).toEqual([{ x: 4, label: "pit", color: expect.any(String) }]);
    });
});
