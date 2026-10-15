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

/** An optional lap-trace channel (g-forces, per-wheel slip / temps) and whether the session has data for it. */
export interface LapExtra {
  key: string
  label: string
  unit: string
  per_wheel: boolean
  available: boolean
  reason: string | null
  channels: string[]
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

/* ---- Live race engineer (telemetria_server/live/engineer.py `view()`) ---- */

export type EngineerPhase = "idle" | "balance" | "quali" | "long_run" | "done"
export type EngineerVariant = "1" | "2"
export type EngineerVerdict = "1" | "2" | "same"
export type EngineerStrength = "slight" | "clear"
export type EngineerConfidence = "none" | "medium" | "high"
export type EngineerRole = "baseline" | "change" | "start" | "final"

export interface EngineerAnswer {
  verdict: EngineerVerdict
  strength: EngineerStrength
  tags: string[]
  note?: string | null
}
export interface EngineerSector {
  sector: number
  delta_s: number
}
export interface EngineerCornerRow {
  corner: number
  name: string
  phase: "entry" | "mid" | "exit"
  /** Variant 2 minus variant 1 (corrected); negative = variant 2 faster there. */
  delta_s: number
  understeer_delta_deg: number | null
  /** Exit only: change of mean rear |slip ratio| on throttle (fraction, 0.01 = 1 %). */
  traction_delta: number | null
}
export interface EngineerTagCheck {
  tag: string
  delta_s: number
  agrees: boolean | null
  text: string
}
export interface EngineerResult {
  pair: number
  label: string
  variants: Record<EngineerVariant, string | number | null>
  /** Corrected variant 2 minus variant 1; negative = variant 2 faster. */
  delta_s: number | null
  noise_s: number | null
  confidence: EngineerConfidence
  measurable: boolean
  text: string
  stopwatch_winner: EngineerVariant | null
  n: Record<EngineerVariant, number>
  sectors: EngineerSector[]
  /** Top corner / phase differences; missing or empty without corner profiles. */
  corners?: EngineerCornerRow[]
  tag_check?: EngineerTagCheck[]
  deg_s_per_lap: number | null
  deg_source: string | null
  your_answer: EngineerAnswer | null
  agreement: "agree" | "disagree" | null
  agreement_text: string | null
  roles: Partial<Record<EngineerVariant, EngineerRole>> | null
  proposed_winner: EngineerVariant | null
}
export interface EngineerHistoryRow {
  n: number
  kind: "param" | "quali" | "skipped"
  param: string
  label: string
  variants?: Record<string, string | number | null> | null
  roles?: Record<string, string> | null
  counted?: Record<string, number> | null
  delta_s?: number | null
  noise_s?: number | null
  confidence?: EngineerConfidence | null
  your_answer?: EngineerAnswer | null
  winner: EngineerVariant | null
  winner_role?: string | null
  outcome: "changed" | "kept" | "same" | "skipped"
}
export interface EngineerRevert {
  key: string
  param: string
  label: string
  from: string | number
  to: string | number
  race_s: number | null
  quali_s: number | null
  combined_s: number
  text: string
}
export interface EngineerLongRunLap {
  lap: number
  time_s: number | null
  corrected_s: number | null
  wear_pct: number | null
  age: number
}
export interface EngineerLongRun {
  compound: number | null
  label: string | null
  laps: EngineerLongRunLap[]
  target: number
  wear_pct_per_lap: number | null
  pace_deg_s_per_lap: number | null
}
export interface EngineerView {
  phase: EngineerPhase
  program: "short" | "full"
  track: string | null
  session_type: string | null
  in_garage: boolean
  budget: { total_s: number | null; left_s: number | null }
  param: { key: string; label: string; unit: string; index: number; of: number } | null
  variants: Record<EngineerVariant, string | number | null> | null
  variant_text: Record<EngineerVariant, string> | null
  instruction: string | null
  run: { variant: EngineerVariant | null; counted: Record<EngineerVariant, number>; target: number; lap: number }
  detected: { variant: EngineerVariant | null; warning: string | null }
  tyre_hint: string | null
  question: { pending: boolean; awaiting_confirm: boolean; proposed: EngineerVariant | null; tags: string[] }
  last_result: EngineerResult | null
  history: EngineerHistoryRow[]
  settled: Record<string, { label: string; value: string | number; new: boolean }>
  revert_proposal: EngineerRevert | null
  long_run: EngineerLongRun | null
  feed: { t: number; text: string }[]
}

// ---------------------------------------------------------------- corners

export interface CornerMetrics {
  time_s: Num
  entry_kmh: Num
  vmin_kmh: Num
  exit_kmh: Num
  brake_m: Num
  trail_m: Num
  trail_s: Num
  throttle_m: Num
}

export type SpeedClass = "slow" | "medium" | "fast"

export interface CornerDef {
  id: number
  name: string
  start_m: number
  end_m: number
  apex_m: number
  vmin_kmh: number
  speed_class: SpeedClass
  merged_from: number[]
}

/** Understeer index per phase (deg, front minus rear |slip angle|, positive = understeer), rear slip on exit, lock-up counts per wheel. */
export interface CornerBalance {
  entry: Num
  mid: Num
  exit: Num
  traction: Num
  lockups: Record<string, number>
}

export type Phase = "entry" | "mid" | "exit"

export interface Lockup {
  wheel: "FL" | "FR" | "RL" | "RR"
  distance_m: number
  length_m: number
  min_slip_ratio: number
  corner: { id: number; name: string } | null
  /** Only on the session view. */
  lap?: number
}

/** Fields shared by /corners (selected lap) and /balance (median over clean laps). */
export interface BalanceFields {
  balance_available: boolean
  balance_reason: string | null
  /** Typical understeer index per phase; labels and colours are relative to it. */
  balance_baseline: Record<Phase, number>
  balance_summary: string | null
  lockups: Lockup[]
}

export interface BalancePayload extends BalanceFields {
  track: string
  session_id: number
  laps: number
  lap_numbers: number[]
  corners: (CornerBalance & { id: number; name: string; speed_class: SpeedClass })[]
}

export interface CornerReportRow extends CornerDef {
  balance: CornerBalance | null
  focus: CornerMetrics
  ref: CornerMetrics
  delta: CornerMetrics
  phases: Record<"entry" | "mid" | "exit", [number, number]>
  callouts: string[]
}

export interface CornersPayload extends BalanceFields {
  track: string
  session_id: number
  lap: number
  reference: { session: number; lap: number }
  corners_source: { session: number | null; lap: number | null; built_at: string }
  corners: CornerReportRow[]
  lap_delta: number
  sum_corner_delta: number
  straights_delta: number
  start_delta: number
}

export interface TrackCornersPayload {
  track: string
  corners: CornerDef[]
  source_session: number | null
  source_lap: number | null
  built_at: string
}

// --- Setups page: library setups per track and the offline duel ---

export interface SetupRunRow {
  session_id: number
  session_type: string
  run: number
  first_lap: number
  last_lap: number
  n_laps: number
  n_clean: number
  compound: number | null
  compound_label: string
  state: string
  kind: string
  fuel_kg: number | null
  pace_s: number | null
  best_s: number | null
  wear_pct_per_lap: number | null
}

export interface SetupCandidate {
  fingerprint: string
  name: string | null
  n_runs: number
  n_clean: number
  sessions: number[]
  last_driven: string
  runs: SetupRunRow[]
}

export interface SetupsPayload {
  track: string
  setups: SetupCandidate[]
}

export type DuelTieBreak = "stopwatch" | "balance" | "feel" | "none"

export interface DuelBalancePhase {
  deg: number | null
  relative: number | null
  label: string | null
}

export interface DuelBalance {
  entry: DuelBalancePhase
  mid: DuelBalancePhase
  exit: DuelBalancePhase
  distance: number | null
}

export interface DuelContestant {
  key: string
  name: string
  n_laps: number
  rank: number
  race_pace_s: number
  quali_pace_s: number
  wear_pct_per_lap: number | null
  race_cost_s: number
  score_s: number
  delta_s: number
  balance: DuelBalance | null
  sessions?: number[]
}

export interface DuelRanking {
  contestants: DuelContestant[]
  order: string[]
  winner: string
  tie_break: DuelTieBreak
  decided: boolean
  same_session: boolean
  noise_s: number
  pairs: { a: string; b: string; gap_s: number; measurable: boolean }[]
  weights: { race: number; quali: number }
  cost_source: "model" | "fallback" | "none"
  cost_note: string
  callouts: string[]
}

export interface DuelResult {
  track: string
  mode: "offline"
  duel_id?: number
  fingerprints: string[]
  names: Record<string, string>
  comparable: boolean
  reasons: string[]
  pairs: { a: string; b: string; comparable: boolean; reason: string | null }[]
  condition: { state: string; compound: number | null; compound_label: string } | null
  correction?: { deg_s_per_lap: number; deg_source: string; fuel_s_per_kg: number }
  balance_note?: string | null
  min_clean_laps: number
  ranking: DuelRanking | null
}
