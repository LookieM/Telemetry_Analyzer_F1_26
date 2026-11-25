const KEY = "telemetria.lapExtras";
export function loadExtras() {
    try {
        const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
        return Array.isArray(raw) ? raw.filter((k) => typeof k === "string") : [];
    }
    catch {
        return [];
    }
}
export function saveExtras(keys) {
    try {
        localStorage.setItem(KEY, JSON.stringify(keys));
    }
    catch {
        /* storage unavailable: the choice just is not remembered */
    }
}
/** The picked extras this session can actually show (nothing until availability is known). */
export function usableExtras(picked, info) {
    if (!info)
        return [];
    const ok = new Set(info.filter((e) => e.available).map((e) => e.key));
    return info.map((e) => e.key).filter((k) => ok.has(k) && picked.includes(k));
}
