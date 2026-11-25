import { describe, expect, it } from "vitest";
import { buildAnswer, commandError, cornerRowLine, tagCheckLine, engineerPanel, fmtBudget, fmtDelta, stopwatchLine, tagLabel, toggleTag, validateAnswer, variantValue } from "./engineer";
const TAGS = ["entry_slow", "traction", "kerbs", "confidence"];
function view(over = {}) {
    return {
        phase: "balance",
        program: "short",
        track: "Miami",
        session_type: "FP1",
        in_garage: false,
        budget: { total_s: 1080, left_s: 900 },
        param: { key: "wing_setup_0", label: "Front wing", unit: "", index: 1, of: 1 },
        variants: { "1": 28, "2": 25 },
        variant_text: { "1": "Front wing 28", "2": "Front wing 25" },
        instruction: "Set Variant 2: Front wing 25",
        run: { variant: "2", counted: { "1": 3, "2": 0 }, target: 3, lap: 0 },
        detected: { variant: null, warning: null },
        tyre_hint: null,
        question: { pending: false, awaiting_confirm: false, proposed: null, tags: TAGS },
        last_result: null,
        history: [],
        settled: {},
        revert_proposal: null,
        long_run: null,
        feed: [],
        ...over,
    };
}
describe("engineerPanel", () => {
    it("shows start for no view and idle", () => {
        expect(engineerPanel(null)).toBe("start");
        expect(engineerPanel(view({ phase: "idle" }))).toBe("start");
    });
    it("follows the phase and the question state", () => {
        expect(engineerPanel(view())).toBe("run");
        expect(engineerPanel(view({ phase: "quali" }))).toBe("quali");
        expect(engineerPanel(view({ phase: "long_run" }))).toBe("long_run");
        expect(engineerPanel(view({ phase: "done" }))).toBe("done");
        expect(engineerPanel(view({ question: { pending: true, awaiting_confirm: false, proposed: null, tags: TAGS } }))).toBe("question");
        expect(engineerPanel(view({ question: { pending: false, awaiting_confirm: true, proposed: "2", tags: TAGS } }))).toBe("confirm");
    });
    it("a revert proposal wins over everything", () => {
        const r = { key: "k", param: "k", label: "Front wing", from: 28, to: 25, race_s: -0.1, quali_s: 0.3, combined_s: 0.02, text: "x" };
        expect(engineerPanel(view({ phase: "quali", revert_proposal: r, question: { pending: true, awaiting_confirm: true, proposed: "1", tags: TAGS } }))).toBe("revert");
    });
});
describe("formatting", () => {
    it("formats the budget as m:ss", () => {
        expect(fmtBudget(900)).toBe("15:00");
        expect(fmtBudget(61.4)).toBe("1:01");
        expect(fmtBudget(-5)).toBe("0:00");
        expect(fmtBudget(null)).toBe("—");
    });
    it("formats signed deltas with a real minus", () => {
        expect(fmtDelta(0.1234)).toBe("+0.123");
        expect(fmtDelta(-0.05, 2)).toBe("−0.05");
        expect(fmtDelta(0.0001, 2)).toBe("0.00");
        expect(fmtDelta(null)).toBe("—");
    });
    it("words the stopwatch result", () => {
        expect(stopwatchLine({ delta_s: -0.2, noise_s: 0.1, measurable: true, stopwatch_winner: "2" })).toBe("Variant 2 faster by 0.200 s/lap (noise ±0.10 s)");
        expect(stopwatchLine({ delta_s: 0.04, noise_s: 0.1, measurable: false, stopwatch_winner: null })).toContain("No measurable difference");
        expect(stopwatchLine({ delta_s: null, noise_s: null, measurable: false, stopwatch_winner: null })).toContain("No stopwatch");
    });
    it("labels tags, with a readable fallback", () => {
        expect(tagLabel("braking_lockups")).toBe("Brake lock-ups");
        expect(tagLabel("some_new_tag")).toBe("Some new tag");
    });
    it("picks the variant text, then the number, then reference", () => {
        expect(variantValue(view(), "1")).toBe("Front wing 28");
        expect(variantValue({ variant_text: null, variants: { "1": 3, "2": null } }, "1")).toBe("3");
        expect(variantValue({ variant_text: null, variants: { "1": 3, "2": null } }, "2")).toBe("reference");
    });
    it("explains command failures", () => {
        expect(commandError(409, "Not in practice")).toBe("Not in practice");
        expect(commandError(503, "x")).toContain("disabled");
        expect(commandError(401, "x")).toContain("token");
        expect(commandError(null, "")).toBe("Command failed");
    });
});
describe("answers", () => {
    it("limits tags to three and toggles off", () => {
        let t = [];
        for (const x of ["entry_slow", "traction", "kerbs", "confidence"])
            t = toggleTag(t, x);
        expect(t).toEqual(["entry_slow", "traction", "kerbs"]);
        expect(toggleTag(t, "traction")).toEqual(["entry_slow", "kerbs"]);
    });
    it("validates verdict, strength and tags", () => {
        expect(validateAnswer({ verdict: null, strength: "clear", tags: [] }, TAGS)).toMatch(/Pick/);
        expect(validateAnswer({ verdict: "1", strength: null, tags: [] }, TAGS)).toMatch(/strong/);
        expect(validateAnswer({ verdict: "same", strength: "slight", tags: ["nope"] }, TAGS)).toMatch(/Unknown/);
        expect(validateAnswer({ verdict: "1", strength: "clear", tags: TAGS }, TAGS)).toMatch(/At most/);
        expect(validateAnswer({ verdict: "2", strength: "clear", tags: ["kerbs"] }, TAGS)).toBeNull();
    });
    it("builds the request body, dropping an empty note", () => {
        expect(buildAnswer({ verdict: "2", strength: "slight", tags: ["kerbs"], note: "  " })).toEqual({ verdict: "2", strength: "slight", tags: ["kerbs"] });
        expect(buildAnswer({ verdict: "1", strength: "clear", tags: [], note: " snappy " }).note).toBe("snappy");
    });
});
describe("corner A/B lines", () => {
    it("words a corner row with the parts that exist", () => {
        expect(cornerRowLine({ corner: 4, name: "T4", phase: "exit", delta_s: -0.08, understeer_delta_deg: 0.4, traction_delta: -0.012 })).toBe("T4 exit: 2 −0.08 s, rear slip −1.2 %, understeer +0.4°");
        expect(cornerRowLine({ corner: 2, name: "T2-T3", phase: "entry", delta_s: 0.06, understeer_delta_deg: null, traction_delta: null })).toBe("T2-T3 entry: 2 +0.06 s");
        expect(cornerRowLine({ corner: 1, name: "T1", phase: "mid", delta_s: 0.0004, understeer_delta_deg: -0.01, traction_delta: null })).toBe("T1 mid: 2 0.00 s, understeer 0.0°");
    });
    it("marks agreement, disagreement and neutral tag checks", () => {
        const t = { tag: "exit_slow", delta_s: -0.1, text: "Exit of slow corners: Variant 2 is 0.10 s faster there" };
        expect(tagCheckLine({ ...t, agrees: true })).toMatchObject({ mark: "✓", cls: "agree" });
        expect(tagCheckLine({ ...t, agrees: false })).toMatchObject({ mark: "✗", cls: "disagree" });
        expect(tagCheckLine({ ...t, agrees: null })).toMatchObject({ mark: "·", cls: "none", text: t.text });
    });
});
