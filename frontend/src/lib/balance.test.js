import { describe, expect, it } from "vitest";
import { balanceColor, balanceLabel, balanceUnavailable, buildBalanceColumns, isSpinning, lockupCounts, lockupSummary, lockupText, relativeIndex } from "./balance";
const baseline = { entry: 2, mid: 3, exit: 0.2 };
describe("relative index and labels", () => {
    it("subtracts the typical value of the phase", () => {
        expect(relativeIndex(5, "mid", baseline)).toBe(2);
        expect(relativeIndex(null, "mid", baseline)).toBeNull();
    });
    it("labels by thresholds on both sides", () => {
        expect(balanceLabel(0)).toBe("neutral");
        expect(balanceLabel(1)).toBe("slight understeer");
        expect(balanceLabel(2.5)).toBe("understeer");
        expect(balanceLabel(-1)).toBe("slight oversteer");
        expect(balanceLabel(-2.5)).toBe("oversteer");
        expect(balanceLabel(null)).toBe("no data");
    });
});
describe("balanceColor", () => {
    const rgb = (c) => (c ? c.match(/\d+/g).map(Number) : []);
    it("is warm for understeer, cool for oversteer, grey in the middle, none without data", () => {
        const [ur, , ub] = rgb(balanceColor(3));
        const [or, , ob] = rgb(balanceColor(-3));
        const [mr, , mb] = rgb(balanceColor(0));
        expect(ur).toBeGreaterThan(ub);
        expect(ob).toBeGreaterThan(or);
        expect(Math.abs(mr - mb)).toBeLessThan(20);
        expect(balanceColor(null)).toBeNull();
    });
    it("saturates beyond the scale", () => {
        expect(balanceColor(10)).toBe(balanceColor(3));
    });
});
describe("buildBalanceColumns", () => {
    it("makes one column per corner with relative labels and tolerates missing balance", () => {
        const cols = buildBalanceColumns([
            { id: 1, name: "T1", balance: { entry: 2, mid: 6, exit: -2, traction: 0.12, lockups: { FL: 1 } } },
            { id: 2, name: "T2", balance: null },
        ], baseline);
        expect(cols.map((c) => c.name)).toEqual(["T1", "T2"]);
        expect(cols[0].phases.entry.label).toBe("neutral");
        expect(cols[0].phases.mid.label).toBe("understeer");
        expect(cols[0].phases.exit.label).toBe("oversteer");
        expect(cols[0].lockups).toEqual({ FL: 1 });
        expect(cols[1].phases.mid.color).toBeNull();
        expect(cols[1].traction).toBeNull();
    });
});
describe("traction and lock-ups", () => {
    const l = (wheel, d, extra = {}) => ({ wheel, distance_m: d, length_m: 6, min_slip_ratio: -0.3, corner: null, ...extra });
    it("flags a spinning rear", () => {
        expect(isSpinning(0.12)).toBe(true);
        expect(isSpinning(0.05)).toBe(false);
        expect(isSpinning(null)).toBe(false);
    });
    it("counts and summarises per wheel, front first", () => {
        const list = [l("RR", 1), l("FL", 2), l("FL", 3)];
        expect(lockupCounts(list)).toEqual({ RR: 1, FL: 2 });
        expect(lockupSummary(list)).toBe("FL ×2 · RR ×1");
        expect(lockupSummary([])).toBe("no lock-ups");
    });
    it("describes where a lock-up happened", () => {
        expect(lockupText(l("FL", 1240.4, { corner: { id: 4, name: "T4" }, length_m: 5.6, lap: 7 }))).toBe("FL at 1240 m (T4), 6 m long, lap 7");
        expect(lockupText(l("RR", 300, { length_m: 0.2 }))).toBe("RR at 300 m, 1 m long");
    });
});
describe("balanceUnavailable", () => {
    it("returns the reason only when balance is not available", () => {
        expect(balanceUnavailable(undefined)).toBeNull();
        expect(balanceUnavailable({ balance_available: true, balance_reason: null })).toBeNull();
        expect(balanceUnavailable({ balance_available: false, balance_reason: "no slip" })).toBe("no slip");
        expect(balanceUnavailable({ balance_available: false, balance_reason: null })).toBe("No balance data");
    });
});
