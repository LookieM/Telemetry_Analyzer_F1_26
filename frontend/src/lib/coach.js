export const ACTION_LABEL = {
    drive: "Drive",
    setup: "Setup",
    manage: "Manage",
    observe: "Observe",
};
/** The remaining callouts grouped by domain (alphabetical), each group in score order. */
export function groupByDomain(items) {
    const by = new Map();
    for (const it of items) {
        const list = by.get(it.domain) ?? [];
        list.push(it);
        by.set(it.domain, list);
    }
    return [...by.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([domain, list]) => ({ domain, items: [...list].sort((x, y) => y.score - x.score) }));
}
export function titleCase(s) {
    return s ? s[0].toUpperCase() + s.slice(1) : s;
}
