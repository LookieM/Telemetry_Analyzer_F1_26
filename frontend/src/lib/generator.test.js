import { describe, expect, it } from "vitest";
import { confidenceClass, confidenceText, evidenceText, generatedBaselineRequest, profileRows, profileSourceLabel } from "./generator";
const entry = (o = {}) => ({
    value: 27, display: 27, unit: "", label: "Front wing", source: "blend", confidence: "medium", weight: 0.9, prior: 30,
    evidence: [
        { track: "Spielberg", source: "baseline", value: 33, offset: 3, found: 36, own: false, similarity: 0.82, weight: 0.82, name: null },
        { track: "Zandvoort", source: "settled", value: 25, offset: null, found: 25, own: true, similarity: 0.71, weight: 0.57, name: null },
    ],
    ...o,
});
describe("confidence badges", () => {
    it("says prior only for low confidence without evidence", () => {
        expect(confidenceText(entry({ confidence: "low", evidence: [] }))).toBe("Low – prior only");
        expect(confidenceText(entry({ confidence: "low" }))).toBe("Low");
        expect(confidenceText(entry())).toBe("Medium");
        expect(confidenceText(entry({ confidence: "high" }))).toBe("High");
        expect(confidenceText(entry({ source: "meta", confidence: "high", evidence: [] }))).toBe("Meta");
        expect(confidenceText(entry({ source: "consumption", evidence: [] }))).toBe("Measured");
    });
    it("maps to a colour class", () => {
        expect([confidenceClass("low"), confidenceClass("medium"), confidenceClass("high")]).toEqual(["bad", "warn", "good"]);
    });
});
describe("evidenceText", () => {
    it("lists the sources, similarity and the prior", () => {
        expect(evidenceText(entry())).toBe("Front wing 27: Spielberg baseline: +3 vs its typical → 33 here (similarity 0.82), Zandvoort settled 25 (similarity 0.71); prior 30");
    });
    it("converts evidence to game units through the display scale", () => {
        const e = entry({ label: "Diff on-throttle", value: 0.78, display: 78, unit: "%", prior: 0.65, evidence: [{ track: "Monza", source: "duel", value: 0.7, offset: 0.12, found: 0.8, own: false, similarity: 0.5, weight: 0.5, name: null }] });
        expect(evidenceText(e)).toBe("Diff on-throttle 78%: Monza duel winner: +12% vs its typical → 70% here (similarity 0.50); prior 65%");
    });
    it("is honest when there is no evidence, meta or measured", () => {
        expect(evidenceText(entry({ evidence: [], source: "prior" }))).toBe("Front wing 27: prior only, no results on other tracks yet (30)");
        expect(evidenceText(entry({ source: "meta", evidence: [] }))).toBe("Front wing 27: kept at the F1 26 meta");
        expect(evidenceText(entry({ source: "consumption", evidence: [], label: "Fuel load", unit: "kg", display: 34, value: 34 }))).toBe("Fuel load 34 kg: from your measured consumption");
    });
});
const profile = { track: "Monza", source: "driven", lap_length_m: 5793, reverse_of: null, slow_frac: 0.0488, medium_frac: 0.1235, fast_frac: 0.0535, full_throttle_frac: 0.7729, heavy_braking_zones: 4, heavy_braking_estimated: false, corner_count: 11 };
describe("profile", () => {
    it("rows and source label", () => {
        expect(profileRows(profile).map((r) => `${r.label} ${r.text}`)).toEqual(["Slow corners 5%", "Medium corners 12%", "Fast corners 5%", "Full throttle 77%", "Heavy braking zones 4", "Lap length 5.79 km"]);
        expect(profileRows({ ...profile, heavy_braking_estimated: true })[4].text).toBe("4 (estimated)");
        expect(profileSourceLabel(profile)).toBe("From your driving");
        expect(profileSourceLabel({ source: "catalogue" })).toBe("Estimated from the catalogue");
    });
});
describe("generatedBaselineRequest", () => {
    it("carries values, source, name and per-parameter confidence", () => {
        const g = { setup: { wing_setup_0: entry(), arb_setup_0: entry({ value: 11, confidence: "low" }) }, first_test: { key: "arb_setup_0", label: "Front anti-roll bar", confidence: "low", text: "t" } };
        const r = generatedBaselineRequest(g, new Date("2026-10-15T10:00:00Z"));
        expect(r).toEqual({ setup: { wing_setup_0: 27, arb_setup_0: 11 }, source: "generator", name: "Generated 2026-10-15", meta: { confidence: { wing_setup_0: "medium", arb_setup_0: "low" }, first_test: g.first_test } });
    });
});
