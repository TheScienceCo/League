import { IngestButton } from "@/components/ingest-button";
import { Badge } from "@/components/ui";
import { formatDate, formatPercent, roleLabel, tierLabel } from "@/lib/format";
import type { PlayerProfile, PlayerSummary } from "@/lib/types";

export function PlayerHeader({
  player,
  riotId,
  platform,
  profile,
}: {
  player: PlayerSummary;
  riotId: string;
  platform: string;
  profile: PlayerProfile | null;
}) {
  const solo = player.ranks.find((r) => r.queue_type === "RANKED_SOLO_5x5") ?? player.ranks[0];
  return (
    <header className="mb-5 flex flex-wrap items-start justify-between gap-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{riotId}</h1>
          <Badge tone="accent">{platform.toUpperCase()}</Badge>
          {solo?.tier && (
            <Badge>
              {solo.tier}
              {solo.division ? ` ${solo.division}` : ""} · {solo.league_points} LP
            </Badge>
          )}
          {profile && profile.games_analyzed > 0 && (
            <Badge>{tierLabel(profile.tier_group)} cohort</Badge>
          )}
        </div>
        <p className="mt-1 text-sm text-ink-muted">
          {player.summoner_level ? `Level ${player.summoner_level} · ` : ""}
          {profile && profile.games_analyzed > 0 ? (
            <>
              {profile.games_analyzed} games analysed
              {profile.win_rate !== null && ` · ${formatPercent(profile.win_rate)} win rate`}
              {profile.primary_role && ` · mostly ${roleLabel(profile.primary_role)}`}
            </>
          ) : (
            "No matches ingested yet"
          )}
          {player.last_ingested_at && ` · updated ${formatDate(player.last_ingested_at)}`}
        </p>
      </div>
      <IngestButton riotId={riotId} platform={platform} count={20} />
    </header>
  );
}
