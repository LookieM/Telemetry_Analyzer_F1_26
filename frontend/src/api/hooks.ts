import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api, qs } from "./client"
import type {
  AllocationPayload,
  TyreSetsPayload,
  BaselinePayload,
  BaselineRequest,
  ChannelsPayload,
  CoachPayload,
  ComparePayload,
  DuelResult,
  BalancePayload,
  CornersPayload,
  TrackCornersPayload,
  ImportResult,
  InventoryRow,
  LapExtra,
  LibraryStats,
  MapPayload,
  OptimisePayload,
  OptimiseRequest,
  OverridesPayload,
  ReviewPayload,
  SessionDetail,
  SessionMeta,
  SetupsPayload,
  Targets,
  TrackModel,
  TrackCatalog,
  TyresPayload,
  GeneratedSetup,
  TrackProfile,
} from "./types"

export const useLibraryStats = () => useQuery({ queryKey: ["stats"], queryFn: () => api.get<LibraryStats>("/library/stats") })

export const useSessions = () => useQuery({ queryKey: ["sessions"], queryFn: () => api.get<SessionMeta[]>("/sessions") })

export const useSession = (id: number, enabled = true) =>
  useQuery({ queryKey: ["session", id], queryFn: () => api.get<SessionDetail>(`/sessions/${id}`), enabled: enabled && Number.isFinite(id) && id > 0 })

export const useLapChannels = (id: number, lap: number | null, channels: string[] | null, enabled = true, extras: string[] = []) =>
  useQuery({
    queryKey: ["channels", id, lap, channels?.join(",") ?? "", extras.join(",")],
    queryFn: () => api.get<ChannelsPayload>(`/sessions/${id}/laps/${lap}/channels${qs({ channels: channels?.join(","), extras: extras.join(",") || undefined })}`),
    enabled: enabled && lap != null,
    placeholderData: keepPreviousData,
  })

export const useCompare = (id: number, lap: number | null, refLap: number | null, refSession: number | null, enabled = true, extras: string[] = []) =>
  useQuery({
    queryKey: ["compare", id, lap, refLap, refSession, extras.join(",")],
    queryFn: () => api.get<ComparePayload>(`/sessions/${id}/compare${qs({ lap, ref_lap: refLap, ref_session: refSession, extras: extras.join(",") || undefined })}`),
    enabled: enabled && lap != null && refLap != null,
    placeholderData: keepPreviousData,
  })

export const useMap = (id: number, lap: number | null, refLap: number | null, refSession: number | null, color: string) =>
  useQuery({
    queryKey: ["map", id, lap, refLap, refSession, color],
    queryFn: () => api.get<MapPayload>(`/sessions/${id}/map${qs({ lap, ref_lap: refLap, ref_session: refSession, color })}`),
    enabled: lap != null,
    placeholderData: keepPreviousData,
  })

export const useCorners = (id: number, lap: number | null, refLap: number | null, refSession: number | null, enabled = true) =>
  useQuery({
    queryKey: ["corners", id, lap, refLap, refSession],
    queryFn: () => api.get<CornersPayload>(`/sessions/${id}/corners${qs({ lap, ref_lap: refLap, ref_session: refSession })}`),
    enabled: enabled && lap != null && refLap != null,
    placeholderData: keepPreviousData,
    retry: false,
  })

/** Balance per corner and phase as the median over the session's clean laps. */
export const useBalance = (id: number, enabled = true) =>
  useQuery({
    queryKey: ["balance", id],
    queryFn: () => api.get<BalancePayload>(`/sessions/${id}/balance`),
    enabled: enabled && Number.isFinite(id) && id > 0,
    retry: false,
  })

/** Session read + ranked engineer callouts over the whole session (all probable laps, PB as reference). */
export const useCoach = (id: number) =>
  useQuery({
    queryKey: ["coach", id],
    queryFn: () => api.get<CoachPayload>(`/sessions/${id}/coach`),
    enabled: Number.isFinite(id) && id > 0,
    staleTime: 5 * 60_000,
  })

export const useLapExtras = (id: number) =>
  useQuery({
    queryKey: ["lap-extras", id],
    queryFn: () => api.get<LapExtra[]>(`/sessions/${id}/lap-extras`),
    staleTime: Infinity,
  })

export const useInventory = (id: number, enabled = true) =>
  useQuery({
    queryKey: ["inventory", id],
    queryFn: () => api.get<InventoryRow[]>(`/sessions/${id}/channels/inventory`),
    enabled,
    staleTime: Infinity,
  })

export const useTyres = (id: number, wearLimit: number | null) =>
  useQuery({
    queryKey: ["tyres", id, wearLimit],
    queryFn: () => api.get<TyresPayload>(`/sessions/${id}/tyres${qs({ wear_limit: wearLimit })}`),
    placeholderData: keepPreviousData,
  })

export const useCompoundModel = (track: string | null, state: string, wearLimit: number | null) =>
  useQuery({
    queryKey: ["compound-model", track, state, wearLimit],
    queryFn: () => api.get<TrackModel>(`/tracks/${encodeURIComponent(track ?? "")}/compound-model${qs({ state, wear_limit: wearLimit })}`),
    enabled: !!track,
  })

export const useTrackCatalog = () => useQuery({ queryKey: ["track-catalog"], queryFn: () => api.get<TrackCatalog>("/tracks") })

export const useAllocation = (track: string | null) =>
  useQuery({
    queryKey: ["allocation", track],
    queryFn: () => api.get<AllocationPayload>(`/tracks/${encodeURIComponent(track ?? "")}/allocation`),
    enabled: !!track,
  })

export const useReview = (id: number, state: string | null) =>
  useQuery({
    queryKey: ["review", id, state],
    queryFn: () => api.get<ReviewPayload>(`/sessions/${id}/strategy-review${qs({ state })}`),
  })

export const useOptimise = (req: OptimiseRequest | null) =>
  useQuery({
    queryKey: ["optimise", req],
    queryFn: () => api.send<OptimisePayload>("POST", "/strategy/optimise", req),
    enabled: req != null,
    placeholderData: keepPreviousData,
  })

export const useOverrides = (track: string | null, state: string) =>
  useQuery({
    queryKey: ["overrides", track, state],
    queryFn: () => api.get<OverridesPayload>(`/tracks/${encodeURIComponent(track ?? "")}/strategy-overrides${qs({ state })}`),
    enabled: !!track,
  })

/** Mutations that change what the library / models show invalidate every cached query. */
function useInvalidating<TVars, TData>(fn: (v: TVars) => Promise<TData>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries() })
}

export const usePatchSession = () =>
  useInvalidating((v: { id: number; session_type?: string; conditions?: string; track_state?: string; condition_notes?: string; notes?: string }) => {
    const { id, ...body } = v
    return api.send<SessionMeta>("PATCH", `/sessions/${id}`, body)
  })

export const useDeleteSession = () => useInvalidating((id: number) => api.send<{ deleted: number }>("DELETE", `/sessions/${id}`))

export const useImportFile = () =>
  useInvalidating((v: { file: File; session_type?: string; conditions?: string; notes?: string }) => {
    const form = new FormData()
    form.set("file", v.file)
    if (v.session_type) form.set("session_type", v.session_type)
    if (v.conditions) form.set("conditions", v.conditions)
    if (v.notes) form.set("notes", v.notes)
    return api.upload<ImportResult>("/import", form)
  })

export const useSaveTargets = () =>
  useInvalidating(
    (v: { code: number; kind: string; temp_lo: number; temp_hi: number; hot_front_psi: number | null; hot_rear_psi: number | null }) => {
      const { code, kind, ...body } = v
      return api.send<Targets>("PUT", `/compounds/${code}/targets${qs({ kind })}`, body)
    },
  )

export const useSaveAllocation = () =>
  useInvalidating((v: { track: string; soft: number | null; medium: number | null; hard: number | null }) => {
    const { track, ...body } = v
    return api.send<AllocationPayload>("PUT", `/tracks/${encodeURIComponent(track)}/allocation`, body)
  })

export const useClearAllocation = () =>
  useInvalidating((track: string) => api.send<AllocationPayload>("DELETE", `/tracks/${encodeURIComponent(track)}/allocation`))

export const useSaveOverrides = () =>
  useInvalidating((v: { track: string } & OptimiseRequest) =>
    api.send<OverridesPayload>("PUT", `/tracks/${encodeURIComponent(v.track)}/strategy-overrides`, {
      state: v.state,
      params: v.params,
      specs: v.specs,
    }),
  )

export const useClearOverrides = () =>
  useInvalidating((v: { track: string; state: string }) =>
    api.send<OverridesPayload>("DELETE", `/tracks/${encodeURIComponent(v.track)}/strategy-overrides${qs({ state: v.state })}`),
  )

export const useSaveTyreSets = () =>
  useInvalidating((v: { track: string; sets: { compound: number; wear: number }[] }) =>
    api.send<TyreSetsPayload>("PUT", `/tracks/${encodeURIComponent(v.track)}/tyre-sets`, { sets: v.sets }),
  )

export const useClearTyreSets = () =>
  useInvalidating((track: string) => api.send<TyreSetsPayload>("DELETE", `/tracks/${encodeURIComponent(track)}/tyre-sets`))

/** Rebuild a track's corners from one lap; every cached analysis refetches against the new corner set. */
export const useRebuildCorners = () =>
  useInvalidating((v: { track: string; session: number; lap: number }) =>
    api.send<TrackCornersPayload>("POST", `/tracks/${encodeURIComponent(v.track)}/corners/rebuild`, { session: v.session, lap: v.lap }),
  )

// --- Setups page ---

export const useTrackSetups = (track: string | null) =>
  useQuery({
    queryKey: ["setups", track],
    queryFn: () => api.get<SetupsPayload>(`/tracks/${encodeURIComponent(track ?? "")}/setups`),
    enabled: !!track,
    staleTime: 60_000,
  })

export function useNameSetup(track: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { fingerprint: string; name: string }) =>
      api.send<{ fingerprint: string; name: string | null }>("PUT", `/setups/${v.fingerprint}/name`, { track, name: v.name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["setups", track] }),
  })
}

export const useRunDuel = (track: string) =>
  useMutation({ mutationFn: (fingerprints: string[]) => api.send<DuelResult>("POST", `/tracks/${encodeURIComponent(track)}/duel`, { fingerprints }) })

// --- Track baseline ---

export const useTrackBaseline = (track: string | null) =>
  useQuery({
    queryKey: ["baseline", track],
    queryFn: () => api.get<BaselinePayload>(`/tracks/${encodeURIComponent(track ?? "")}/baseline`),
    enabled: !!track,
  })

export function useSetBaseline(track: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: BaselineRequest) => api.send<BaselinePayload>("POST", `/tracks/${encodeURIComponent(track)}/baseline`, body),
    onSuccess: (data) => qc.setQueryData(["baseline", track], data),
  })
}

export const useTrackProfile = (track: string | null) =>
  useQuery({
    queryKey: ["track-profile", track],
    queryFn: () => api.get<TrackProfile>(`/tracks/${encodeURIComponent(track ?? "")}/profile`),
    enabled: !!track,
    staleTime: 5 * 60_000,
  })

/** The generated setup is computed on demand (enable it when the page should show it). */
export const useGeneratedSetup = (track: string | null, enabled: boolean) =>
  useQuery({
    queryKey: ["generated-setup", track],
    queryFn: () => api.get<GeneratedSetup>(`/tracks/${encodeURIComponent(track ?? "")}/generated-setup`),
    enabled: !!track && enabled,
    staleTime: 60_000,
  })
