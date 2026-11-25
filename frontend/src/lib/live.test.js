import { describe, expect, it } from "vitest";
import { gapLabel, liveSections, pushDelta } from "./live";
describe("pushDelta", () => {
    it("appends increasing distances and ignores null deltas", () => {
        let p = [];
        p = pushDelta(p, 10, 0.1);
        p = pushDelta(p, 20, null);
        p = pushDelta(p, 30, -0.2);
        expect(p).toEqual([
            [10, 0.1],
            [30, -0.2],
        ]);
    });
    it("starts a new lap when the distance wraps", () => {
        let p = [
            [5000, 0.5],
            [6900, 0.6],
        ];
        p = pushDelta(p, 30, 0.01);
        expect(p).toEqual([[30, 0.01]]);
    });
    it("caps the length", () => {
        let p = [];
        for (let i = 1; i <= 50; i++)
            p = pushDelta(p, i, 0, 10);
        expect(p.length).toBe(10);
        expect(p[9][0]).toBe(50);
    });
});
describe("gapLabel", () => {
    it("signs gaps", () => {
        expect(gapLabel(-3.86)).toBe("−3.9");
        expect(gapLabel(0.18)).toBe("+0.2");
        expect(gapLabel(0)).toBe("0.0");
        expect(gapLabel(null)).toBe("—");
    });
});
describe("liveSections", () => {
    it("race: strategy, no engineer", () => {
        expect(liveSections("Race", false, false)).toEqual({ strategy: true, engineer: false });
    });
    it("practice: engineer, no strategy", () => {
        for (const t of ["FP1", "FP2", "FP3", "Test", "Practice", "Short Practice"])
            expect(liveSections(t, false, false)).toEqual({ strategy: false, engineer: true });
    });
    it("quali: neither", () => {
        for (const t of ["Quali", "Qualifying", "Short Quali"])
            expect(liveSections(t, false, false)).toEqual({ strategy: false, engineer: false });
    });
    it("a running program or duel stays visible in any session", () => {
        expect(liveSections("Race", true, false).engineer).toBe(true);
        expect(liveSections("Quali", false, true).engineer).toBe(true);
        expect(liveSections("Race", true, false).strategy).toBe(true);
    });
});
