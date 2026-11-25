import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./client";
export const useLibraryStats = () => useQuery({ queryKey: ["stats"], queryFn: () => api.get("/library/stats") });
export const useSessions = () => useQuery({ queryKey: ["sessions"], queryFn: () => api.get("/sessions") });
export const useSession = (id, enabled = true) => useQuery({ queryKey: ["session", id], queryFn: () => api.get(`/sessions/${id}`), enabled: enabled && Number.isFinite(id) && id > 0 });
export const useLapChannels = (id, lap, channels, enabled = true, extras = []) => useQuery({
    queryKey: ["channels", id, lap, channels?.join(",") ?? "", extras.join(",")],
    queryFn: () => api.get(`/sessions/${id}/laps/${lap}/channels${qs({ channels: channels?.join(","), extras: extras.join(",") || undefined })}`),
    enabled: enabled && lap != null,
    placeholderData: keepPreviousData,
});
export const useCompare = (id, lap, refLap, refSession, enabled = true, extras = []) => useQuery({
    queryKey: ["compare", id, lap, refLap, refSession, extras.join(",")],
    queryFn: () => api.get(`/sessions/${id}/compare${qs({ lap, ref_lap: refLap, ref_session: refSession, extras: extras.join(",") || undefined })}`),
    enabled: enabled && lap != null && refLap != null,
    placeholderData: keepPreviousData,
});
export const useMap = (id, lap, refLap, refSession, color) => useQuery({
    queryKey: ["map", id, lap, refLap, refSession, color],
    queryFn: () => api.get(`/sessions/${id}/map${qs({ lap, ref_lap: refLap, ref_session: refSession, color })}`),
    enabled: lap != null,
    placeholderData: keepPreviousData,
});
export const useCorners = (id, lap, refLap, refSession, enabled = true) => useQuery({
    queryKey: ["corners", id, lap, refLap, refSession],
    queryFn: () => api.get(`/sessions/${id}/corners${qs({ lap, ref_lap: refLap, ref_session: refSession })}`),
    enabled: enabled && lap != null && refLap != null,
    placeholderData: keepPreviousData,
    retry: false,
});
/** Balance per corner and phase as the median over the session's clean laps. */
export const useBalance = (id, enabled = true) => useQuery({
    queryKey: ["balance", id],
    queryFn: () => api.get(`/sessions/${id}/balance`),
    enabled: enabled && Number.isFinite(id) && id > 0,
    retry: false,
});
/** Session read + ranked engineer callouts over the whole session (all probable laps, PB as reference). */
export const useCoach = (id) => useQuery({
    queryKey: ["coach", id],
    queryFn: () => api.get(`/sessions/${id}/coach`),
    enabled: Number.isFinite(id) && id > 0,
    staleTime: 5 * 60_000,
});
export const useLapExtras = (id) => useQuery({
    queryKey: ["lap-extras", id],
    queryFn: () => api.get(`/sessions/${id}/lap-extras`),
    staleTime: Infinity,
});
export const useInventory = (id, enabled = true) => useQuery({
    queryKey: ["inventory", id],
    queryFn: () => api.get(`/sessions/${id}/channels/inventory`),
    enabled,
    staleTime: Infinity,
});
export const useTyres = (id, wearLimit) => useQuery({
    queryKey: ["tyres", id, wearLimit],
    queryFn: () => api.get(`/sessions/${id}/tyres${qs({ wear_limit: wearLimit })}`),
    placeholderData: keepPreviousData,
});
export const useCompoundModel = (track, state, wearLimit) => useQuery({
    queryKey: ["compound-model", track, state, wearLimit],
    queryFn: () => api.get(`/tracks/${encodeURIComponent(track ?? "")}/compound-model${qs({ state, wear_limit: wearLimit })}`),
    enabled: !!track,
});
export const useTrackCatalog = () => useQuery({ queryKey: ["track-catalog"], queryFn: () => api.get("/tracks") });
export const useAllocation = (track) => useQuery({
    queryKey: ["allocation", track],
    queryFn: () => api.get(`/tracks/${encodeURIComponent(track ?? "")}/allocation`),
    enabled: !!track,
});
export const useReview = (id, state) => useQuery({
    queryKey: ["review", id, state],
    queryFn: () => api.get(`/sessions/${id}/strategy-review${qs({ state })}`),
});
export const useOptimise = (req) => useQuery({
    queryKey: ["optimise", req],
    queryFn: () => api.send("POST", "/strategy/optimise", req),
    enabled: req != null,
    placeholderData: keepPreviousData,
});
export const useOverrides = (track, state) => useQuery({
    queryKey: ["overrides", track, state],
    queryFn: () => api.get(`/tracks/${encodeURIComponent(track ?? "")}/strategy-overrides${qs({ state })}`),
    enabled: !!track,
});
/** Mutations that change what the library / models show invalidate every cached query. */
function useInvalidating(fn) {
    const qc = useQueryClient();
    return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries() });
}
export const usePatchSession = () => useInvalidating((v) => {
    const { id, ...body } = v;
    return api.send("PATCH", `/sessions/${id}`, body);
});
export const useDeleteSession = () => useInvalidating((id) => api.send("DELETE", `/sessions/${id}`));
export const useImportFile = () => useInvalidating((v) => {
    const form = new FormData();
    form.set("file", v.file);
    if (v.session_type)
        form.set("session_type", v.session_type);
    if (v.conditions)
        form.set("conditions", v.conditions);
    if (v.notes)
        form.set("notes", v.notes);
    return api.upload("/import", form);
});
export const useSaveTargets = () => useInvalidating((v) => {
    const { code, kind, ...body } = v;
    return api.send("PUT", `/compounds/${code}/targets${qs({ kind })}`, body);
});
export const useSaveAllocation = () => useInvalidating((v) => {
    const { track, ...body } = v;
    return api.send("PUT", `/tracks/${encodeURIComponent(track)}/allocation`, body);
});
export const useClearAllocation = () => useInvalidating((track) => api.send("DELETE", `/tracks/${encodeURIComponent(track)}/allocation`));
export const useSaveOverrides = () => useInvalidating((v) => api.send("PUT", `/tracks/${encodeURIComponent(v.track)}/strategy-overrides`, {
    state: v.state,
    params: v.params,
    specs: v.specs,
}));
export const useClearOverrides = () => useInvalidating((v) => api.send("DELETE", `/tracks/${encodeURIComponent(v.track)}/strategy-overrides${qs({ state: v.state })}`));
export const useSaveTyreSets = () => useInvalidating((v) => api.send("PUT", `/tracks/${encodeURIComponent(v.track)}/tyre-sets`, { sets: v.sets }));
export const useClearTyreSets = () => useInvalidating((track) => api.send("DELETE", `/tracks/${encodeURIComponent(track)}/tyre-sets`));
/** Rebuild a track's corners from one lap; every cached analysis refetches against the new corner set. */
export const useRebuildCorners = () => useInvalidating((v) => api.send("POST", `/tracks/${encodeURIComponent(v.track)}/corners/rebuild`, { session: v.session, lap: v.lap }));
// --- Setups page ---
export const useTrackSetups = (track) => useQuery({
    queryKey: ["setups", track],
    queryFn: () => api.get(`/tracks/${encodeURIComponent(track ?? "")}/setups`),
    enabled: !!track,
    staleTime: 60_000,
});
export function useNameSetup(track) {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (v) => api.send("PUT", `/setups/${v.fingerprint}/name`, { track, name: v.name }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ["setups", track] }),
    });
}
export const useRunDuel = (track) => useMutation({ mutationFn: (fingerprints) => api.send("POST", `/tracks/${encodeURIComponent(track)}/duel`, { fingerprints }) });
// --- Track baseline ---
export const useTrackBaseline = (track) => useQuery({
    queryKey: ["baseline", track],
    queryFn: () => api.get(`/tracks/${encodeURIComponent(track ?? "")}/baseline`),
    enabled: !!track,
});
export function useSetBaseline(track) {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (body) => api.send("POST", `/tracks/${encodeURIComponent(track)}/baseline`, body),
        onSuccess: (data) => qc.setQueryData(["baseline", track], data),
    });
}
export const useTrackProfile = (track) => useQuery({
    queryKey: ["track-profile", track],
    queryFn: () => api.get(`/tracks/${encodeURIComponent(track ?? "")}/profile`),
    enabled: !!track,
    staleTime: 5 * 60_000,
});
/** The generated setup is computed on demand (enable it when the page should show it). */
export const useGeneratedSetup = (track, enabled) => useQuery({
    queryKey: ["generated-setup", track],
    queryFn: () => api.get(`/tracks/${encodeURIComponent(track ?? "")}/generated-setup`),
    enabled: !!track && enabled,
    staleTime: 60_000,
});
