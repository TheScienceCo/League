import Link from "next/link";

import { Card, EmptyState, PlayerTabs } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, formatDuration, formatPercent, roleLabel } from "@/lib/format";
import type { MatchListItem, Page as PageType } from "@/lib/types";

import { PlayerHeader } from "../player-header";
import { resolvePlayer, type PlayerRouteParams } from "../player-data";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 20;

export default async function MatchHistoryPage({
  params,
  searchParams,
}: {
  params: Promise<PlayerRouteParams>;
  searchParams: Promise<{ page?: string }>;
}) {
  const routeParams = await params;
  const { page: pageParam } = await searchParams;
  const page = Math.max(1, Number(pageParam ?? "1") || 1);
  const { player, riotId } = await resolvePlayer(routeParams);

  let matches: PageType<MatchListItem> | null = null;
  let profile = null;
  try {
    [matches, profile] = await Promise.all([
      api.matches(player.puuid, PAGE_SIZE, (page - 1) * PAGE_SIZE),
      api.profile(player.puuid).catch(() => null),
    ]);
  } catch {
    matches = null;
  }

  const totalPages = matches ? Math.max(1, Math.ceil(matches.total / PAGE_SIZE)) : 1;
  const base = `/player/${routeParams.platform}/${encodeURIComponent(riotId)}/matches`;

  return (
    <div>
      <PlayerHeader
        player={player}
        riotId={riotId}
        platform={routeParams.platform}
        profile={profile}
      />
      <PlayerTabs platform={routeParams.platform} riotId={riotId} active="matches" />

      {!matches || matches.items.length === 0 ? (
        <EmptyState title="No matches stored">
          Ingest this player’s match history to populate their game log.
        </EmptyState>
      ) : (
        <Card
          title={`${matches.total} matches`}
          subtitle="Per-game derived metrics. Gold and CS differentials are measured against the lane opponent."
        >
          <div className="scroll-x">
            <table className="data">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Result</th>
                  <th>Champion</th>
                  <th>Role</th>
                  <th>Length</th>
                  <th>K/D/A</th>
                  <th>KP</th>
                  <th>CS/min</th>
                  <th>GD@10</th>
                  <th>GD@15</th>
                  <th>Vision</th>
                  <th>RCE</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {matches.items.map((match) => (
                  <tr key={match.match_id}>
                    <td className="whitespace-nowrap text-ink-muted">
                      {formatDate(match.game_start)}
                    </td>
                    <td className={match.win ? "text-good" : "text-bad"}>
                      {match.win ? "Win" : "Loss"}
                    </td>
                    <td>{match.champion_name ?? match.champion_id}</td>
                    <td className="text-ink-muted">{roleLabel(match.team_position)}</td>
                    <td className="stat text-ink-muted">
                      {formatDuration(match.duration_seconds)}
                    </td>
                    <td className="stat">
                      {match.kills}/{match.deaths}/{match.assists}
                    </td>
                    <td className="stat">{formatPercent(match.kill_participation)}</td>
                    <td className="stat">{match.cs_per_min?.toFixed(1) ?? "—"}</td>
                    <td
                      className={`stat ${
                        (match.gold_diff_10 ?? 0) > 0
                          ? "text-good"
                          : (match.gold_diff_10 ?? 0) < 0
                            ? "text-bad"
                            : ""
                      }`}
                    >
                      {match.gold_diff_10 !== null
                        ? `${match.gold_diff_10 > 0 ? "+" : ""}${match.gold_diff_10.toFixed(0)}`
                        : "—"}
                    </td>
                    <td
                      className={`stat ${
                        (match.gold_diff_15 ?? 0) > 0
                          ? "text-good"
                          : (match.gold_diff_15 ?? 0) < 0
                            ? "text-bad"
                            : ""
                      }`}
                    >
                      {match.gold_diff_15 !== null
                        ? `${match.gold_diff_15 > 0 ? "+" : ""}${match.gold_diff_15.toFixed(0)}`
                        : "—"}
                    </td>
                    <td className="stat">{match.vision_score}</td>
                    <td className="stat">{match.rce_raw?.toFixed(2) ?? "—"}</td>
                    <td>
                      <Link
                        href={`/match/${match.match_id}?puuid=${player.puuid}&platform=${routeParams.platform}&riotId=${encodeURIComponent(riotId)}`}
                        className="link whitespace-nowrap text-xs"
                      >
                        Analyse
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <nav className="mt-4 flex items-center justify-between text-sm">
              {page > 1 ? (
                <Link href={`${base}?page=${page - 1}`} className="link">
                  ← Newer
                </Link>
              ) : (
                <span />
              )}
              <span className="text-ink-faint">
                Page {page} of {totalPages}
              </span>
              {page < totalPages ? (
                <Link href={`${base}?page=${page + 1}`} className="link">
                  Older →
                </Link>
              ) : (
                <span />
              )}
            </nav>
          )}
        </Card>
      )}
    </div>
  );
}
