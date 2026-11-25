import { beforeEach, describe, expect, it } from "vitest";
import { EMPTY_GROUP, nearestIndex, selectGroup, useCursorStore } from "./cursor";
describe("cursor store", () => {
    beforeEach(() => useCursorStore.setState({ groups: {} }));
    it("keeps hover and pin per sync group", () => {
        const s = useCursorStore.getState();
        s.setHover("lap", 120, "map");
        s.setPinned("lap", 300);
        s.setHover("stint", 5, "chart");
        const lap = selectGroup("lap")(useCursorStore.getState());
        expect(lap).toEqual({ hoverX: 120, hoverSource: "map", pinnedX: 300 });
        expect(selectGroup("stint")(useCursorStore.getState()).hoverX).toBe(5);
        expect(selectGroup("race")(useCursorStore.getState())).toEqual(EMPTY_GROUP);
    });
    it("clears the hover source when the hover ends but keeps the pin", () => {
        const s = useCursorStore.getState();
        s.setPinned("lap", 42);
        s.setHover("lap", 10, "chart");
        s.setHover("lap", null, "chart");
        expect(selectGroup("lap")(useCursorStore.getState())).toEqual({ hoverX: null, hoverSource: null, pinnedX: 42 });
    });
    it("does not notify when nothing changed", () => {
        const s = useCursorStore.getState();
        s.setHover("lap", 1, "a");
        const before = useCursorStore.getState().groups;
        s.setHover("lap", 1, "a");
        s.setPinned("lap", null);
        expect(useCursorStore.getState().groups).toBe(before);
    });
    it("clearing an already clear hover is a no-op (no render loops)", () => {
        const s = useCursorStore.getState();
        s.setHover("lap", null, "chart-1");
        const first = useCursorStore.getState().groups;
        s.setHover("lap", null, "chart-2");
        expect(useCursorStore.getState().groups).toBe(first);
    });
    it("reset empties a group", () => {
        const s = useCursorStore.getState();
        s.setPinned("lap", 9);
        s.reset("lap");
        expect(selectGroup("lap")(useCursorStore.getState())).toEqual(EMPTY_GROUP);
    });
    it("notifies subscribers of hover changes", () => {
        const seen = [];
        const off = useCursorStore.subscribe((state) => seen.push(selectGroup("lap")(state).hoverX));
        useCursorStore.getState().setHover("lap", 7, "map");
        useCursorStore.getState().setHover("lap", null, "map");
        off();
        expect(seen).toEqual([7, null]);
    });
});
describe("nearestIndex", () => {
    const d = [0, 2, 4, 6, 8, 10];
    it("finds the closest sample", () => {
        expect(nearestIndex(d, 0)).toBe(0);
        expect(nearestIndex(d, 2.9)).toBe(1);
        expect(nearestIndex(d, 3.1)).toBe(2);
        expect(nearestIndex(d, 99)).toBe(5);
        expect(nearestIndex(d, -5)).toBe(0);
    });
    it("handles empty input", () => {
        expect(nearestIndex([], 3)).toBe(-1);
    });
});
