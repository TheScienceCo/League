/** Presentation helpers shared across pages. */

/** Metrics that read as percentages rather than raw ratios. */
const RATE_METRICS = new Set([
  "kill_participation",
  "objective_participation",
  "dragon_participation",
  "baron_herald_participation",
  "time_ahead_share",
  "roam_success_rate",
  "high_risk_exposure_share",
  "objective_setup_score",
  "mean_position_risk",
]);

export function formatMetric(metric: string, value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (RATE_METRICS.has(metric)) return `${(value * 100).toFixed(0)}%`;
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

export function formatSigned(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rounded = value.toFixed(digits);
  return value > 0 ? `+${rounded}` : rounded;
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function ordinal(n: number): string {
  const rounded = Math.round(n);
  const rem10 = rounded % 10;
  const rem100 = rounded % 100;
  if (rem10 === 1 && rem100 !== 11) return `${rounded}st`;
  if (rem10 === 2 && rem100 !== 12) return `${rounded}nd`;
  if (rem10 === 3 && rem100 !== 13) return `${rounded}rd`;
  return `${rounded}th`;
}

export function tierLabel(tierGroup: string): string {
  const labels: Record<string, string> = {
    IRON_BRONZE: "Iron–Bronze",
    SILVER_GOLD: "Silver–Gold",
    PLAT_EMERALD: "Platinum–Emerald",
    DIAMOND: "Diamond",
    MASTER_PLUS: "Master+",
    UNRANKED: "Unranked",
  };
  return labels[tierGroup] ?? tierGroup;
}

export function roleLabel(role: string): string {
  const labels: Record<string, string> = {
    TOP: "Top",
    JUNGLE: "Jungle",
    MIDDLE: "Mid",
    BOTTOM: "Bot",
    UTILITY: "Support",
    UNKNOWN: "Unknown",
  };
  return labels[role] ?? role;
}

export function zoneLabel(zone: string): string {
  return zone
    .split("_")
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

/**
 * Colour for a percentile, where higher is better once `higherIsBetter` has
 * already been applied by the caller.
 */
export function percentileTone(percentile: number | null | undefined): string {
  if (percentile === null || percentile === undefined) return "text-ink-faint";
  if (percentile >= 75) return "text-good";
  if (percentile >= 45) return "text-ink";
  if (percentile >= 25) return "text-warn";
  return "text-bad";
}

/** Percentile adjusted so that "higher is always better". */
export function effectivePercentile(
  percentile: number | null | undefined,
  higherIsBetter: boolean,
): number | null {
  if (percentile === null || percentile === undefined) return null;
  return higherIsBetter ? percentile : 100 - percentile;
}

export const PLATFORMS = [
  "na1", "euw1", "eun1", "kr", "br1", "jp1", "la1", "la2", "oc1", "tr1", "ru",
] as const;

export const TIER_GROUPS = [
  "IRON_BRONZE", "SILVER_GOLD", "PLAT_EMERALD", "DIAMOND", "MASTER_PLUS",
] as const;

export const ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"] as const;
export const PHASES = ["EARLY", "MID", "LATE"] as const;
