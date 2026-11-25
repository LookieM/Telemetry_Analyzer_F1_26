export const MAX_NAME = 40;
export const ORDINAL = ["1st", "2nd", "3rd"];
/** The names typed in the start form: trimmed, cut to the length the server accepts, one per contestant. */
export function duelNames(raw, n) {
    return Array.from({ length: n }, (_, i) => (raw[i] ?? "").trim().slice(0, MAX_NAME));
}
/** Which panel the duel shows for a view (null / idle = start). */
export function duelPanel(v) {
    if (!v || v.phase === "idle")
        return "start";
    if (v.phase === "done")
        return "done";
    if (v.phase === "review")
        return "review";
    return v.question.pending ? "feel" : "run";
}
/** True while a duel owns the card (running, reviewing or just finished). */
export const duelShown = (v) => v != null && v.phase !== "idle";
/** Feel form state: contestant key -> rank (1-based). Giving a rank to one contestant takes it from the other. */
export function assignRank(ranks, key, rank) {
    const out = {};
    for (const [k, r] of Object.entries(ranks))
        if (r !== rank && k !== key)
            out[k] = r;
    out[key] = rank;
    return out;
}
/** Keys best first, or null while the form is incomplete (every key needs a distinct rank 1..n). */
export function feelOrder(ranks, keys) {
    const rs = keys.map((k) => ranks[k]);
    if (rs.some((r) => r == null))
        return null;
    if (new Set(rs).size !== keys.length || rs.some((r) => r < 1 || r > keys.length))
        return null;
    return [...keys].sort((a, b) => ranks[a] - ranks[b]);
}
export function validateFeel(ranks, keys) {
    return feelOrder(ranks, keys) ? null : `Give every setup its own place, 1st to ${ORDINAL[keys.length - 1] ?? keys.length}`;
}
/** "3/4" laps counted against the target. */
export const lapsText = (c) => `${Math.min(c.counted, c.target)}/${c.target}`;
export function statusText(c, v) {
    if (c.skipped)
        return "skipped";
    if (c.on_car)
        return "on the car";
    if (v.next === c.key)
        return "drive now";
    if (c.status === "done")
        return "done";
    if (!c.assigned)
        return "setup not seen yet";
    return "waiting";
}
/** Label of a contestant key (falls back to the key). */
export function labelOf(v, key) {
    return v.contestants.find((c) => c.key === key)?.label ?? key ?? "—";
}
/** One line after a confirmed or stopped duel. */
export function finishedText(v) {
    if (v.winner)
        return `${labelOf(v, v.winner)} is the ${v.track} baseline now (see the Setups page).`;
    return v.ranking
        ? "Duel stopped before a winner was confirmed: the measurements are saved, the baseline is unchanged."
        : "Duel stopped with too little data to rank: what was driven is saved, the baseline is unchanged.";
}
