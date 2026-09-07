/**
 * Types mirroring the backend's API responses.
 *
 * Hand-written rather than generated so the frontend can express exactly the
 * shape it consumes. The backend's OpenAPI schema at /openapi.json is the source
 * of truth; `npm run typecheck` is what keeps this honest.
 */

export interface RankInfo {
  queue_type: string;
  tier: string | null;
  division: string | null;
  league_points: number;
  wins: number;
  losses: number;
  rank_score: number;
  tier_group: string;
  hot_streak: boolean;
}

export interface PlayerSummary {
  puuid: string;
  game_name: string | null;
  tag_line: string | null;
  platform: string;
  profile_icon_id: number | null;
  summoner_level: number | null;
  last_ingested_at: string | null;
  ranks: RankInfo[];
}

export interface MetricValue {
  metric: string;
  label: string;
  value: number | null;
  percentile: number | null;
  cohort_median: number | null;
  cohort_n: number | null;
  higher_is_better: boolean;
}

export interface ConsistencyStats {
  games: number;
  performance_mean: number;
  performance_std: number;
  best_game_z: number;
  worst_game_z: number;
  consistency_rate: number;
}

export interface LeadConversionStats {
  games_with_lead: number;
  leads_converted: number;
  lead_conversion_rate: number | null;
  games_behind: number;
  comebacks: number;
  comeback_rate: number | null;
  cohort_lead_conversion_rate: number | null;
}

export interface RoleSplit {
  role: string;
  games: number;
  wins: number;
  win_rate: number;
  champions: string[];
}

export interface ChampionSplit {
  champion_id: number;
  champion_name: string | null;
  games: number;
  wins: number;
  win_rate: number;
  kda: number;
  cs_per_min: number;
}

export interface PlayerProfile {
  player: PlayerSummary;
  games_analyzed: number;
  win_rate: number | null;
  primary_role: string | null;
  tier_group: string;
  headline_metrics: MetricValue[];
  role_splits: RoleSplit[];
  champion_splits: ChampionSplit[];
  consistency: ConsistencyStats | null;
  lead_conversion: LeadConversionStats | null;
}

export interface MatchListItem {
  match_id: string;
  queue_id: number;
  queue_name: string;
  patch: string;
  game_start: string | null;
  duration_seconds: number;
  win: boolean;
  champion_id: number;
  champion_name: string | null;
  team_position: string;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
  cs_per_min: number | null;
  gold_earned: number;
  vision_score: number;
  kill_participation: number | null;
  gold_diff_10: number | null;
  gold_diff_15: number | null;
  rce_raw: number | null;
  has_timeline: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface CohortComparison {
  metric: string;
  label: string;
  value: number | null;
  percentile: number | null;
  z_score: number | null;
  cohort_mean: number | null;
  cohort_median: number | null;
  cohort_p25: number | null;
  cohort_p75: number | null;
  cohort_n: number;
  cohort_dimensions: Record<string, string | number | null>;
  is_fallback_cohort: boolean;
  games_compared?: number;
}

export interface ResourceConversion {
  rce_raw_mean: number | null;
  rce_z_mean: number | null;
  damage_share_mean: number | null;
  gold_share_mean: number | null;
  percentile: number | null;
  cohort_n: number | null;
  interpretation: string | null;
}

export interface AdvancedStats {
  puuid: string;
  games_analyzed: number;
  tier_group: string;
  context: Record<string, string | number | null>;
  metrics: CohortComparison[];
  resource_conversion: ResourceConversion | null;
}

export interface Position {
  x: number | null;
  y: number | null;
}

export interface TimelinePoint {
  minute: number;
  gold: number;
  xp: number;
  cs: number;
  level: number;
  gold_diff: number | null;
  xp_diff: number | null;
  cs_diff: number | null;
  team_gold_diff: number | null;
  position: Position | null;
}

export interface MatchEvent {
  type: string;
  timestamp_ms: number;
  minute: number;
  involved_player: boolean;
  killer: string | null;
  killer_team_id: number | null;
  victim: string | null;
  assists: number;
  monster_type: string | null;
  monster_sub_type: string | null;
  building_type: string | null;
  lane_type: string | null;
  position: Position | null;
  zone: string | null;
  player_team: number;
}

export interface MatchDeath {
  timestamp_ms: number;
  minute: number;
  position: Position | null;
  zone: string | null;
  killer: string | null;
  assist_count: number;
  solo_death: boolean;
  risk_at_position: number | null;
  team_gold_diff: number | null;
}

export interface ObjectiveSetupRow {
  objective_type: string;
  objective_sub_type: string | null;
  minute: number;
  timestamp_ms: number;
  team_secured: boolean;
  player_credited: boolean;
  distance_30s: number | null;
  distance_60s: number | null;
  distance_90s: number | null;
  arrival_lead_seconds: number | null;
  wards_placed_window: number;
  wards_cleared_window: number;
  deaths_window: number;
  setup_score: number | null;
}

export interface RoamRow {
  start_minute: number;
  end_minute: number;
  target_zone: string;
  kills: number;
  assists: number;
  deaths: number;
  objectives: number;
  gold_gained: number;
  xp_gained: number;
  cs_sacrificed: number;
  value: number;
  expected_value: number | null;
  efficiency: number | null;
  success: boolean;
}

export interface Observation {
  metric: string;
  label: string;
  severity: "strength" | "neutral" | "watch" | "priority";
  headline: string;
  detail: string;
  value: number | null;
  percentile: number | null;
  cohort_n: number;
  salience: number;
}

export interface ParticipantRow {
  participant_id: number;
  puuid: string;
  riot_id: string | null;
  team_id: number;
  win: boolean;
  champion_id: number;
  champion_name: string | null;
  team_position: string;
  champ_level: number;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
  gold_earned: number;
  damage_to_champions: number;
  damage_taken: number;
  vision_score: number;
  wards_placed: number;
  wards_killed: number;
  kill_participation: number | null;
}

export interface MatchAnalysis {
  match: {
    match_id: string;
    platform: string;
    queue_id: number;
    queue_name: string;
    patch: string;
    game_start: string | null;
    duration_seconds: number;
    winning_team_id: number | null;
    has_timeline: boolean;
  };
  player: ParticipantRow;
  lane_opponent: ParticipantRow | null;
  teams: Array<{
    team_id: number;
    win: boolean;
    champion_kills: number;
    dragon_kills: number;
    baron_kills: number;
    herald_kills: number;
    tower_kills: number;
    inhibitor_kills: number;
    first_blood: boolean;
    first_tower: boolean;
  }>;
  participants: ParticipantRow[];
  timeline: TimelinePoint[];
  events: MatchEvent[];
  deaths: MatchDeath[];
  objective_setups: ObjectiveSetupRow[];
  roams: RoamRow[];
  advanced_metrics: Array<{ metric: string; label: string; value: number | null }>;
  cohort_comparisons: CohortComparison[];
  observations: Observation[];
}

export interface RiskCell {
  cell_x: number;
  cell_y: number;
  grid_size: number;
  phase: string;
  role: string;
  tier_group: string;
  exposures: number;
  deaths: number;
  risk: number;
  baseline_risk: number;
  lift: number;
  zone: string | null;
}

export interface HeatmapResponse {
  grid_size: number;
  horizon_seconds: number;
  role: string | null;
  phase: string | null;
  tier_group: string | null;
  cells: RiskCell[];
  disclaimer: string;
}

export interface ZoneRisk {
  zone: string;
  phase: string;
  exposures: number;
  deaths: number;
  risk: number;
  baseline_risk: number;
  lift: number;
  insight: string | null;
}

export interface ZoneRiskResponse {
  role: string | null;
  tier_group: string | null;
  horizon_seconds: number;
  zones: ZoneRisk[];
  disclaimer: string;
}

export interface PlayerSpatial {
  puuid: string;
  grid_size: number;
  matches: number;
  cells: Array<{
    cell_x: number;
    cell_y: number;
    exposures: number;
    deaths: number;
    death_rate: number;
  }>;
  deaths: Array<{ match_id: string; minute: number; x: number; y: number; zone: string }>;
  comparison: {
    player_tier_group: string;
    reference_tier_group: string;
    player_high_risk_share: number | null;
    reference_high_risk_share: number | null;
    player_deaths_above_expected: number | null;
    zones: ZoneRisk[];
  } | null;
  disclaimer: string;
}

export interface BehaviourGap {
  feature: string;
  label: string;
  importance: number;
  rank_correlation: number;
  player_value: number | null;
  player_residual: number | null;
  target_residual: number | null;
  gap_z: number;
  gap_natural: number;
  target_band_average: number | null;
  impact: number;
  higher_is_better: boolean;
  player_percentile: number | null;
  cohort_n: number | null;
}

export interface ModelInfo {
  name?: string;
  version?: string;
  trained_at?: string | null;
  n_samples?: number;
  metrics?: Record<string, number | null>;
}

export interface SkillGapReport {
  puuid: string;
  player_tier_group: string;
  target_tier_group: string;
  games_analyzed: number;
  behaviours: BehaviourGap[];
  model: ModelInfo;
  caveats: string[];
}

export interface RankSeparation {
  model: ModelInfo;
  behaviours: Array<{
    feature: string;
    label: string;
    importance: number;
    rank_correlation: number;
    higher_is_better: boolean;
    tier_means: Record<string, number | null>;
  }>;
}

export interface CohortTableRow {
  metric: string;
  label: string;
  player_value: number | null;
  player_percentile: number | null;
  own_cohort_median: number | null;
  own_cohort_n: number | null;
  target_cohort_mean: number | null;
  target_cohort_median: number | null;
  target_cohort_n: number | null;
  gap_to_target: number | null;
  gap_z: number | null;
  higher_is_better: boolean;
}

export interface CohortTable {
  puuid: string;
  games_analyzed: number;
  player_tier_group: string;
  target_tier_group: string;
  context: Record<string, string | number | null>;
  rows: CohortTableRow[];
}

export interface IngestJob {
  id: string;
  puuid: string;
  platform: string;
  status: string;
  requested_matches: number;
  matches_discovered: number;
  matches_ingested: number;
  matches_skipped: number;
  timelines_ingested: number;
  features_computed: number;
  progress: number;
  error: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
  database: boolean;
  redis: boolean;
  riot_provider: string;
}
