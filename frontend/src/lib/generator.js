import { valueText } from "./baseline";
const CONFIDENCE_LABELS = { low: "Low", medium: "Medium", high: "High" };
/** "Low – prior only", "Medium", "High": the badge text of one parameter. */
export function confidenceText(entry) {
    if (entry.source === "meta")
        return "Meta";
    if (entry.source === "consumption")
        return "Measured";
    const base = CONFIDENCE_LABELS[entry.confidence] ?? entry.confidence;
    return entry.confidence === "low" && entry.evidence.length === 0 ? `${base} – prior only` : base;
}
/** CSS modifier of a badge: green / amber / red. */
export function confidenceClass(c) {
    return c === "high" ? "good" : c === "medium" ? "warn" : "bad";
}
/** A stored-unit value in the game's units (the entry's `display` / `value` ratio carries the Pa -> psi, 0-1 -> % scale). */
export function evidenceShown(entry, ev) {
    return entry.value ? (ev.value * entry.display) / entry.value : ev.value;
}
function shownText(entry, v) {
    return valueText({ value: v, unit: entry.unit });
}
const SOURCE_NOUN = { baseline: "baseline", settled: "settled", duel: "duel winner" };
/** One evidence item: "Hungaroring baseline: +12 vs its typical → 22 here (similarity 0.31)"; an absolute one: "Monza settled 25 (similarity 1.00)". */
export function evidenceItemText(entry, ev) {
    const head = `${ev.track} ${SOURCE_NOUN[ev.source] ?? ev.source}`;
    const sim = `(similarity ${ev.similarity.toFixed(2)})`;
    const shown = shownText(entry, evidenceShown(entry, ev));
    if (ev.offset == null)
        return `${head} ${shown} ${sim}`;
    const scale = entry.value ? entry.display / entry.value : 1;
    const off = ev.offset * scale;
    const dec = entry.unit === "psi" ? 2 : Number.isInteger(Math.round(off * 100) / 100) ? 0 : 2;
    const sign = off > 0 ? "+" : off < 0 ? "−" : "±";
    const unit = entry.unit && entry.unit !== "psi" && entry.unit !== "°" ? (entry.unit.startsWith("%") ? "%" : ` ${entry.unit}`) : entry.unit === "psi" ? " psi" : entry.unit === "°" ? "°" : "";
    return `${head}: ${sign}${Math.abs(off).toFixed(dec)}${unit} vs its typical → ${shown} here ${sim}`;
}
/** "Front wing 27: Spielberg baseline: +3 vs its typical → 33 here (similarity 0.82); prior 30". */
export function evidenceText(entry) {
    const head = `${entry.label} ${shownText(entry, entry.display)}`;
    if (entry.source === "meta")
        return `${head}: kept at the F1 26 meta`;
    if (entry.source === "consumption")
        return `${head}: from your measured consumption`;
    const prior = entry.prior != null ? shownText(entry, evidenceShown(entry, { value: entry.prior })) : null;
    if (entry.evidence.length === 0)
        return `${head}: prior only, no results on other tracks yet${prior ? ` (${prior})` : ""}`;
    return `${head}: ${entry.evidence.map((e) => evidenceItemText(entry, e)).join(", ")}${prior ? `; prior ${prior}` : ""}`;
}
const pct = (x) => `${Math.round(x * 100)}%`;
export function profileSourceLabel(p) {
    return p.source === "driven" ? "From your driving" : "Estimated from the catalogue";
}
/** The class shares, full-throttle share and heavy braking zones as label / text rows. */
export function profileRows(p) {
    return [
        { label: "Slow corners", text: pct(p.slow_frac) },
        { label: "Medium corners", text: pct(p.medium_frac) },
        { label: "Fast corners", text: pct(p.fast_frac) },
        { label: "Full throttle", text: pct(p.full_throttle_frac) },
        { label: "Heavy braking zones", text: `${p.heavy_braking_zones}${p.heavy_braking_estimated ? " (estimated)" : ""}` },
        { label: "Lap length", text: `${(p.lap_length_m / 1000).toFixed(2)} km` },
    ];
}
/** The POST /baseline body for "Make baseline": values, source "generator", per-parameter confidence and the first test. */
export function generatedBaselineRequest(g, now = new Date()) {
    const setup = {};
    const confidence = {};
    for (const [key, e] of Object.entries(g.setup)) {
        setup[key] = e.value;
        confidence[key] = e.confidence;
    }
    return { setup, source: "generator", name: `Generated ${now.toISOString().slice(0, 10)}`, meta: { confidence, first_test: g.first_test } };
}
