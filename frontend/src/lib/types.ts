/** Mirrors `app/schemas/aoe2.py`. */

/** How a number was arrived at. `unavailable` always carries a null value. */
export type Availability = "observed" | "reconstructed" | "inferred" | "unavailable";

export interface Metric {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  availability: Availability;
  note: string | null;
}

export interface BuildOrderEntry {
  timestamp_ms: number;
  building: string;
  x: number | null;
  y: number | null;
}

export interface ResourcePoint {
  timestamp_ms: number;
  /** Food + wood + gold + stone combined; the per-type split is not in a replay. */
  banked: number;
  objects: number;
}

export interface PlayerAnalysis {
  player_number: number;
  name: string;
  civilization: string;
  winner: boolean | null;
  opening: string | null;
  age_timings_ms: Record<string, number>;
  float_by_age: Record<string, number>;
  metrics: Record<string, Metric>;
  build_order: BuildOrderEntry[];
  resource_curve: ResourcePoint[];
  insights: string[];
}

export interface MatchAnalysis {
  replay_id: string;
  filename: string;
  map_name: string | null;
  duration_ms: number;
  version: string | null;
  players: PlayerAnalysis[];
  warnings: string[];
}
