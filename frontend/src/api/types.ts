/** Shapes of the JSON the FastAPI server returns (see telemetria_server/api). null replaces NaN. */

export type Num = number | null
export type Series = Num[]

export interface LibraryStats {
  sessions: number
  tracks: number
  stored_bytes: number
  original_bytes: number
  saved_bytes: number
}

export interface SessionMeta {
  id: number
  created_at: string
  source_name: string
  source_hash?: string
  track: string | null
  car: string | null
  track_length: number | null
  notes: string
  sample_count: number
  lap_count: number
  best_lap: number | null
  best_lap_time: number | null
  telemetry_path?: string
  original_size_bytes: number | null
  stored_size_bytes: number | null
  source_deleted?: number
  session_type: string
  conditions: string
  setup_fingerprint?: string | null
}

export interface LapSummary {
  lap: number
  lap_time: number
  samples?: number
  vmax?: Num
  vavg?: Num
  throttle_full_pct?: Num
  coast_pct?: Num
  brake_pct?: Num
  fuel_used?: Num
  tyre_wear_avg?: Num
  tyre_wear_max?: Num
  tyre_temp_avg?: Num
  compound?: Num
  compound_label?: string
  lockup_samples?: Num
  tyre_age?: Num
  lap_class: string
  pit_stop: boolean
  fresh_set?: boolean
  delta_best: number
  is_best: boolean
}

export interface SessionDetail {
  session: SessionMeta
  laps: LapSummary[]
}

export interface ChannelsPayload {
  session_id: number
  lap: number
  x: number[]
  x_label: string
  channels: Record<string, Series>
  units: Record<string, string>
}

export interface SectorDelta {
  dist_start: number
  dist_end: number
  delta_s: number
  delta_end: number
  sector?: number
  mini_sector?: number
}

export interface ComparePayload {
  session_id: number
  lap: number
  ref_session: number
  ref_lap: number
  lap_distance: number[]
  delta_time: Series
  final_delta: Num
  sectors: SectorDelta[]
  mini_sectors: SectorDelta[]
  // ref_<channel> / cmp_<channel> series, e.g. ref_speed
  [key: string]: unknown
}

export interface MapChannel {
  label: string
  unit: string
  decimals: number
  values: Series
  ref?: Series
}

export interface MapColor {
  values: Series
  min: number
  max: number
  scale: [number, string][]
  label: string
  decimals: number
}

export interface MapPayload {
  x: Series
  y: Series
  d: Series
  channels: MapChannel[]
  cmp_label: string
  ref_label: string
  color: MapColor | null
  labels: { text: string; d: number }[]
  spans: { from: number; to: number; name: string }[]
  outline: { x: number[]; y: number[] } | null
  session_id: number
  lap: number
  ref_lap: number | null
  ref_session: number | null
  track: string | null
  track_length: number | null
}

export interface InventoryRow {
  Group: string
  Channel: string
  Unit: string
  Columns: string
}

export interface Targets {
  compound: number | null
  temp_lo: number
  temp_hi: number
  hot_front_psi: number | null
  hot_rear_psi: number | null
  source: string
}

export type WheelMap = Record<string, number | null>

export interface Stint {
  idx: number
  laps: number[]
  compound: number | null
  push_laps: number[]
  ages: Record<string, number>
}

export interface PressureRow {
  Wheel: string
  [col: string]: string | number | null
}

export interface StintSummary {
  stint: Stint
  deg: { slope: Num; intercept: Num; r2: Num; n: number; cliff_age: Num }
  wear_rate: WheelMap
  limiting_wheel: string | null
  wear_now: Num
  laps_to_limit: Num
  temp_mean: WheelMap
  temp_in_window: WheelMap
  hot_psi: WheelMap
  cold_psi: Record<string, Num>
  warmup_s: Num
  fuel_per_lap: Num
  label: string
  role: string | null
  color: string
  targets: Targets
  pressure: PressureRow[]
}

export interface WheelRow {
  lap: number
  lap_class: string
  stint: number
  age: number
  compound: Num
  lap_time: Num
  fuel_start: Num
  corr_time: Num
  [col: string]: string | number | null
}

export interface AllocationEntry {
  label: string
  role: string | null
  color: string
}

export interface RaceStats {
  fuel_s_per_kg: number
  fuel_pairs: number
  box_wear_pct: number
  n_stops: number
}

export interface TyresPayload {
  session_id: number
  track: string
  state: string
  wear_limit: number
  temp_channel: string | null
  temp_kind: string
  stints: StintSummary[]
  wheel_table: WheelRow[]
  targets: Record<string, Targets>
  allocation: Record<string, AllocationEntry>
  race_stats: RaceStats
}

export interface CompoundModel {
  code: number
  label: string
  color: string
  offset_s: number
  deg_s_per_lap: number
  wear_pct_per_lap: Num
  warmup_s: number
  n_stints: number
  n_laps: number
  source: string
  note: string
  max_laps: Num
}

export interface TrackModel {
  track: string
  state: string
  base_pace_s: Num
  ref_compound: Num
  compounds: Record<string, CompoundModel>
  pit_losses: number[]
  fuel_per_lap: Num
  race_laps_seen: Num
  sources: number[]
  pit_loss: Num
  wear_limit: number
}

export interface CatalogTrack {
  track: string
  length_m: number | null
  full_laps: number | null
  race_laps: number | null
  pit_loss_s: number
  sessions: number
  map: boolean
  named_corners: boolean
  allocation: { source: string; soft: string | null; medium: string | null; hard: string | null }
  game_tyres: boolean
}

export interface TrackCatalog {
  race_share: number
  tracks: CatalogTrack[]
}

export interface AllocationPayload {
  track: string
  source: string
  soft: number | null
  medium: number | null
  hard: number | null
  roles: Record<string, string>
  compounds: Record<string, AllocationEntry>
  options: { code: number; label: string }[]
}

export interface RaceParams {
  laps: number
  pit_loss_s: number
  base_pace_s: number
  fuel_per_lap_kg: number
  fuel_effect_s_per_kg: number
  fuel_margin_laps: number
  wear_limit_pct: number
  sc_pit_factor: number
  require_two_compounds: boolean
  max_stops: number
  window_tolerance_s: number
  start_fuel_kg: number
}

export interface CompoundSpec {
  code: number
  label: string
  color: string
  offset_s: number
  deg_s_per_lap: number
  wear_pct_per_lap: Num
  warmup_s: number
  deg2_s?: number
  source: string
  use: boolean
}

export interface PlanJson {
  compounds: number[]
  stints: number[]
  stops: number
  stop_laps: number[]
  windows: number[][]
  race_time: number
  label: string
  delta_best?: number
}

export interface RaceTrace {
  laps: number[]
  plans: { label: string; lap_times: Series; gap_to_best: Series }[]
  box_laps: number[]
}

export type TableRow = Record<string, string | number | boolean | null>

export interface OptimisePayload {
  track: string
  state: string
  model: TrackModel
  params: RaceParams
  specs: CompoundSpec[]
  notes: Record<string, string>
  sources: number[]
  saved_overrides: boolean
  allocation: Record<string, AllocationEntry>
  plans: PlanJson[]
  best?: PlanJson
  sensitivity: TableRow[]
  calls: TableRow[]
  race_trace: RaceTrace | null
  message: string | null
}

export interface ReviewJson {
  actual: PlanJson
  actual_time: Num
  model_actual_time: number
  best: PlanJson
  strategy_cost_s: number
  execution_s: Num
  missing_laps: number[]
  sc_laps: number[]
  over_limit: { stint: number; compound: number; laps: number; max_laps: number }[]
  actual_lap_times: Series
}

export interface ReviewPayload {
  session_id: number
  track: string
  state: string
  is_race: boolean
  review: ReviewJson | null
  reason: string | null
  game_pit_windows: number[][]
  params?: RaceParams
  allocation?: Record<string, AllocationEntry>
}

export interface OptimiseRequest {
  track: string
  state: string
  params?: Partial<RaceParams>
  specs?: Partial<CompoundSpec>[]
}

export interface OverridesPayload {
  track: string
  state: string
  saved: boolean
  params: Record<string, unknown>
  compounds: Record<string, unknown>
}

export interface ImportResult {
  session_id?: number
  [key: string]: unknown
}
