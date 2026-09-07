import { notFound } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import type { PlayerSummary } from "@/lib/types";

export interface PlayerRouteParams {
  platform: string;
  riotId: string;
}

/**
 * Resolves a route's Riot ID to a stored player.
 *
 * The search endpoint is identity-only and cheap, and it persists the account,
 * so a first-time visit lands on a valid (if empty) profile rather than a 404
 * and the page can offer to ingest matches.
 */
export async function resolvePlayer(params: PlayerRouteParams): Promise<{
  player: PlayerSummary;
  riotId: string;
}> {
  const riotId = decodeURIComponent(params.riotId);
  try {
    const player = await api.searchPlayer(riotId, params.platform);
    return { player, riotId };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}
