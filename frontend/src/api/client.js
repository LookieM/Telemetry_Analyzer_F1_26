export class ApiError extends Error {
    status;
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}
async function request(url, init) {
    const res = await fetch(url, init);
    if (!res.ok) {
        let detail = res.statusText;
        try {
            const body = await res.json();
            if (body?.detail)
                detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        }
        catch {
            /* not JSON */
        }
        throw new ApiError(res.status, detail);
    }
    return (await res.json());
}
export function qs(params) {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params))
        if (v !== undefined && v !== null && v !== "")
            sp.set(k, String(v));
    const s = sp.toString();
    return s ? `?${s}` : "";
}
export const api = {
    get: (path) => request(`/api${path}`),
    send: (method, path, body) => request(`/api${path}`, {
        method,
        headers: body === undefined ? undefined : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
    }),
    upload: (path, form) => request(`/api${path}`, { method: "POST", body: form }),
};
/** Live race engineer commands; each returns the new engineer view (409 = refused, `detail` is the reason). */
/** Live setup duel commands; each returns the new duel view (409 = refused, `detail` is the reason). */
export const duelApi = {
    start: (n, names) => api.send("POST", "/live/duel/start", { n, names }),
    rank: (order, note) => api.send("POST", "/live/duel/rank", note ? { order, note } : { order }),
    confirm: (winner) => api.send("POST", "/live/duel/confirm", { winner }),
    skip: () => api.send("POST", "/live/duel/skip"),
    stop: () => api.send("POST", "/live/duel/stop"),
};
export const engineerApi = {
    start: (program, minutes) => api.send("POST", "/live/engineer/start", minutes ? { program, minutes } : { program }),
    answer: (a) => api.send("POST", "/live/engineer/answer", a),
    confirm: (winner) => api.send("POST", "/live/engineer/confirm", { winner }),
    revert: (accept) => api.send("POST", "/live/engineer/revert", { accept }),
    skip: () => api.send("POST", "/live/engineer/skip"),
    nextPhase: () => api.send("POST", "/live/engineer/next-phase"),
    stop: () => api.send("POST", "/live/engineer/stop"),
};
export const baselineApi = {
    set: (track, body) => api.send("POST", `/tracks/${encodeURIComponent(track)}/baseline`, body),
};
