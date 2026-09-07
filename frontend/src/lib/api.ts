/**
 * Typed API client.
 *
 * Server components call the backend directly (`API_INTERNAL_URL`); client
 * components go through the Next rewrite at `/api/backend/*`, so the browser
 * never needs to know the backend's address and there is no CORS negotiation.
 */

import type {
  AdvancedStats,
  CohortTable,
  HealthResponse,
  HeatmapResponse,
  IngestJob,
  MatchAnalysis,
  MatchListItem,
  Page,
  PlayerProfile,
  PlayerSpatial,
  PlayerSummary,
  RankSeparation,
  SkillGapReport,
  ZoneRiskResponse,
} from "./types";

const SERVER_BASE = `${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/api/v1`;
const CLIENT_BASE = "/api/backend";

const isServer = typeof window === "undefined";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string = "error",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions extends RequestInit {
  /** Seconds to cache on the server. 0 disables caching for live data. */
  revalidate?: number;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { revalidate, ...init } = options;
  const base = isServer ? SERVER_BASE : CLIENT_BASE;
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    ...(isServer ? { next: { revalidate: revalidate ?? 30 } } : {}),
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    let code = "error";
    try {
      const body = await response.json();
      if (body?.error) {
        message = body.error.message ?? message;
        code = body.error.code ?? code;
      } else if (body?.detail) {
        message = typeof body.detail === "string" ? body.detail : message;
      }
    } catch {
      // Non-JSON error body; the status-derived message stands.
    }
    throw new ApiError(message, response.status, code);
  }
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  health: () => request<HealthResponse>("/health", { revalidate: 0 }),

  searchPlayer: (riotId: string, platform: string) =>
    request<PlayerSummary>(`/players/search${query({ riot_id: riotId, platform })}`, {
      revalidate: 0,
    }),

  listPlayers: (limit = 24) => request<PlayerSummary[]>(`/players${query({ limit })}`),

  profile: (puuid: string) => request<PlayerProfile>(`/players/${puuid}`),

  matches: (puuid: string, limit = 20, offset = 0) =>
    request<Page<MatchListItem>>(`/players/${puuid}/matches${query({ limit, offset })}`),

  advanced: (puuid: string) => request<AdvancedStats>(`/players/${puuid}/advanced`),

  cohort: (puuid: string, targetTierGroup?: string) =>
    request<CohortTable>(
      `/players/${puuid}/cohort${query({ target_tier_group: targetTierGroup })}`,
    ),

  trend: (puuid: string, window = 5) =>
    request<Array<Record<string, number | string | boolean | null>>>(
      `/players/${puuid}/trend${query({ window })}`,
    ),

  playerSpatial: (puuid: string, limitMatches = 40) =>
    request<PlayerSpatial>(`/players/${puuid}/spatial${query({ limit_matches: limitMatches })}`),

  skillGap: (puuid: string, targetTierGroup?: string, topN = 5) =>
    request<SkillGapReport>(
      `/players/${puuid}/skill-gap${query({ target_tier_group: targetTierGroup, top_n: topN })}`,
    ),

  rankSeparation: (topN = 15) =>
    request<RankSeparation>(`/skill-gap/rank-separation${query({ top_n: topN })}`),

  matchAnalysis: (matchId: string, puuid: string) =>
    request<MatchAnalysis>(`/matches/${matchId}${query({ puuid })}`),

  heatmap: (params: {
    role?: string;
    phase?: string;
    tier_group?: string;
    min_exposures?: number;
  }) => request<HeatmapResponse>(`/spatial/heatmap${query(params)}`),

  zoneRisk: (params: { role?: string; tier_group?: string; min_exposures?: number }) =>
    request<ZoneRiskResponse>(`/spatial/zones${query(params)}`),

  startIngest: (body: {
    riot_id?: string;
    puuid?: string;
    platform: string;
    count: number;
    resolve_participant_ranks?: boolean;
  }) =>
    request<IngestJob>("/ingest", {
      method: "POST",
      body: JSON.stringify(body),
      revalidate: 0,
    }),

  job: (jobId: string) => request<IngestJob>(`/ingest/${jobId}`, { revalidate: 0 }),
};
