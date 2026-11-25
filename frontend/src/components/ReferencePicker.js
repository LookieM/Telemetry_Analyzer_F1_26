import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/** Reference-lap choice shared by the Laps and Corners tabs: none, a lap in this session, or a lap of another session of the same track. */
import { useEffect, useMemo, useState } from "react";
import { useSession, useSessions } from "../api/hooks";
import { formatLapTime } from "../lib/format";
import { bestLapNumber, lapLabel, pbSession } from "../lib/sessions";
export function LapSelect({ laps, value, onChange, label }) {
    return (_jsxs("label", { className: "field", children: [label, _jsx("select", { value: value ?? "", onChange: (e) => onChange(Number(e.target.value)), "aria-label": label, children: laps.map((l) => (_jsx("option", { value: l.lap, children: lapLabel(l, formatLapTime) }, l.lap))) })] }));
}
/** State of the reference pickers; resets to `initialMode` and the session's best lap when the session changes. */
export function useReference(detail, initialMode) {
    const { session, laps } = detail;
    const sessions = useSessions();
    const best = bestLapNumber(laps);
    const [mode, setMode] = useState(initialMode);
    const [refLap, setRefLap] = useState(best);
    const [refSessionId, setRefSessionId] = useState(null);
    useEffect(() => {
        setMode(initialMode);
        setRefLap(bestLapNumber(laps));
        setRefSessionId(null);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [session.id]);
    const sameTrack = useMemo(() => (sessions.data ?? []).filter((s) => s.track === session.track && s.id !== session.id), [sessions.data, session.track, session.id]);
    const pb = useMemo(() => pbSession(sessions.data?.filter((s) => s.track === session.track) ?? []), [sessions.data, session.track]);
    const refDetail = useSession(refSessionId ?? 0, mode === "session" && refSessionId != null);
    const refLaps = mode === "session" ? (refDetail.data?.laps ?? []) : laps;
    const chooseMode = (m) => {
        setMode(m);
        if (m === "session") {
            const pick = pb && pb.id !== session.id ? pb.id : (sameTrack[0]?.id ?? null);
            setRefSessionId(pick);
            setRefLap(null); // filled once that session's laps arrive
        }
        else {
            setRefSessionId(null);
            setRefLap(best);
        }
    };
    useEffect(() => {
        if (mode === "session" && refDetail.data && (refLap == null || !refDetail.data.laps.some((l) => l.lap === refLap))) {
            setRefLap(bestLapNumber(refDetail.data.laps));
        }
    }, [mode, refDetail.data, refLap]);
    const selection = useMemo(() => {
        if (mode === "none" || refLap == null || (mode === "session" && (!refDetail.data || refSessionId == null)))
            return null;
        return { session: mode === "session" ? refSessionId : null, lap: refLap };
    }, [mode, refLap, refDetail.data, refSessionId]);
    return {
        mode,
        chooseMode,
        refLap,
        setRefLap,
        refSessionId,
        setRefSession: (id) => {
            setRefSessionId(id);
            setRefLap(null);
        },
        sameTrack,
        pb,
        refLaps,
        selection,
    };
}
/** The reference selects (type, session, lap); `modes` lists the reference types on offer. */
export function ReferenceFields({ choice, modes }) {
    const { mode, chooseMode, refSessionId, setRefSession, sameTrack, pb, refLaps, refLap, setRefLap } = choice;
    const names = { none: "None", lap: "Lap in this session", session: "Another session" };
    return (_jsxs(_Fragment, { children: [_jsxs("label", { className: "field", children: ["Reference", _jsx("select", { value: mode, onChange: (e) => chooseMode(e.target.value), "aria-label": "Reference type", children: modes.map((m) => (_jsx("option", { value: m, disabled: m === "session" && sameTrack.length === 0, children: names[m] }, m))) })] }), mode === "session" && (_jsxs("label", { className: "field", children: ["Reference session", _jsx("select", { value: refSessionId ?? "", onChange: (e) => setRefSession(Number(e.target.value)), "aria-label": "Reference session", children: sameTrack.map((s) => (_jsxs("option", { value: s.id, children: ["#", s.id, " \u00B7 ", s.session_type || "—", " \u00B7 ", s.lap_count, " laps \u00B7 best ", formatLapTime(s.best_lap_time), pb?.id === s.id ? " ★ PB" : ""] }, s.id))) })] })), mode !== "none" && refLaps.length > 0 && _jsx(LapSelect, { laps: refLaps, value: refLap, onChange: setRefLap, label: "Reference lap" })] }));
}
