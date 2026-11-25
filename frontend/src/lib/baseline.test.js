import { describe, expect, it, vi } from "vitest";
import { copyText, copyToClipboard, engineerBaselineName, groupValues, offerSummary, sourceLabel, valueText } from "./baseline";
const g = (group, label, value, unit = "", key = label) => ({ group, key, label, value, unit });
const items = [g("Aero", "Front wing", 25), g("Aero", "Rear wing", 20), g("Transmission", "Diff on-throttle", 65, "%"), g("Geometry", "Front camber", -3.5, "°"), g("Tyres", "Front left pressure", 25.5, "psi"), g("Fuel", "Fuel load", 30, "kg")];
describe("valueText", () => {
    it("formats in game units", () => {
        expect(valueText(items[0])).toBe("25");
        expect(valueText(items[2])).toBe("65%");
        expect(valueText(items[3])).toBe("−3.50°");
        expect(valueText(items[4])).toBe("25.50 psi");
        expect(valueText(items[5])).toBe("30 kg");
        expect(valueText(g("Suspension", "x", 1.5))).toBe("1.50");
        expect(valueText(g("Brakes", "Brake bias", 57, "% front"))).toBe("57%");
    });
});
describe("groupValues", () => {
    it("keeps the order and merges consecutive groups", () => {
        expect(groupValues(items).map((x) => [x.group, x.items.length])).toEqual([["Aero", 2], ["Transmission", 1], ["Geometry", 1], ["Tyres", 1], ["Fuel", 1]]);
        expect(groupValues([])).toEqual([]);
    });
});
describe("copyText", () => {
    it("lists groups and plain minus signs", () => {
        const t = copyText("Hungaroring baseline: My setup", items);
        expect(t.split("\n").slice(0, 5)).toEqual(["Hungaroring baseline: My setup", "", "Aero", "  Front wing: 25", "  Rear wing: 20"]);
        expect(t).toContain("  Front camber: -3.50°");
        expect(t).toContain("  Front left pressure: 25.50 psi");
    });
});
describe("labels", () => {
    it("names sources, the engineer baseline and the offer", () => {
        expect(sourceLabel("duel")).toBe("Setup duel");
        expect(engineerBaselineName(new Date("2026-10-15T12:00:00Z"))).toBe("Engineer 2026-10-15");
        expect(offerSummary({ final: {}, changed: [{ key: "k", label: "Front wing", from: 25, to: 28 }, { key: "j", label: "Diff", from: 65, to: 70 }] })).toBe("Front wing 25 → 28, Diff 65 → 70");
    });
});
describe("copyToClipboard", () => {
    it("is false instead of throwing when the clipboard refuses", async () => {
        vi.stubGlobal("navigator", { clipboard: { writeText: () => Promise.reject(new Error("denied")) } });
        expect(await copyToClipboard("x")).toBe(false);
        vi.stubGlobal("navigator", { clipboard: { writeText: () => Promise.resolve() } });
        expect(await copyToClipboard("x")).toBe(true);
        vi.unstubAllGlobals();
    });
});
