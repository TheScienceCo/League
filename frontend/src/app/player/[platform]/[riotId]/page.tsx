import Link from "next/link";

import { TrendChart } from "@/components/charts";
import { Card, Disclaimer, EmptyState, PercentileBar, PlayerTabs, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import {
  effectivePercentile,
  formatMetric,
  formatPercent,
  ordinal,
  percentileTone,
  roleLabel,
} from "@/lib/format";
import type { MatchListItem, PlayerProfile } from "@/lib/types";

import { PlayerHeader } from "./player-header";
import { resolvePlayer, type PlayerRouteParams } from "./player-data";

export const dynamic = "force-dynamic";

export default async function PlayerOverviewPage({
  params,
}: {
  params: Promise<PlayerRouteParams>;
}) {
  const routeParams = await params;
  const { player, riotId } = await resolvePlayer(routeParams);

  let profile: PlayerProfile | null = null;
  let recent: MatchListItem[] = [];
  let trend: Array<Record<string, number | string | boolean | null>> = [];
  try {
    profile = await api.profile(player.puuid);
    const [matches, trendData] = await Promise.all([
      api.matches(player.puuid, 5),
      api.trend(player.puuid, 5),
    ]);
    recent = matches.items;
    trend = trendData;
  } catch {
    profile = null;
  }

  const hasData = profile !== null && profile.games_analyzed > 0;

  return (
    <div>
      <PlayerHeader
        player={player}
        riotId={riotId}
        platform={routeParams.platform}
        profile={profile}
      />
      <PlayerTabs platform={routeParams.platform} riotId={riotId} active="overview" />

      {!hasData ? (
        <EmptyState title="No analysed games yet">
          Use “Ingest recent matches” above to pull this player’s match history and
          timelines. Everything on these pages is derived from that data.
        </EmptyState>
      ) : (
        <div className="space-y-5">
          <Card
            title="Derived metrics vs peer cohort"
            subtitle="Each game is compared against players in the same role, champion, rank band, patch and game length. The percentile shown is the median across games."
          >
            <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
              {profile!.headline_metrics.map((metric) => {
                const effective = effectivePercentile(
                  metric.percentile,
                  metric.higher_is_better,
                );
                return (
                  <div key={metric.metric}>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="label">{metric.label}</span>
                      <span className={`text-xs ${percentileTone(effective)}`}>
                        {effective !== null ? ordinal(effective) : "—"}
                      </span>
                    </div>
                    <div className="stat mt-1 text-lg">
                      {formatMetric(metric.metric, metric.value)}
                    </div>
                    <div className="mt-1.5">
                      <PercentileBar value={effective} />
                    </div>
                    <div className="mt-1 text-xs text-ink-faint">
                      cohort median {formatMetric(metric.metric, metric.cohort_median)}
                      {metric.cohort_n ? ` · n=${metric.cohort_n}` : ""}
                    </div>
                  </div>
                );
              })}
            </div>
            <Disclaimer>
              Percentiles are computed per game against that game’s own cohort and
              then summarised, so a player who mostly plays one role is not judged
              against another.
            </Disclaimer>
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            {profile!.consistency && (
              <Card
                title="Consistency"
                subtitle="Spread of a cohort-normalised composite across games. Lower spread means more repeatable."
              >
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Stat
                    label="Mean form"
                    value={profile!.consistency.performance_mean.toFixed(2)}
                    hint="z vs cohort"
                  />
                  <Stat
                    label="Std deviation"
                    value={profile!.consistency.performance_std.toFixed(2)}
                    hint="game to game"
                  />
                  <Stat
                    label="Within 1σ"
                    value={formatPercent(profile!.consistency.consistency_rate)}
                    hint="of own mean"
                  />
                  <Stat
                    label="Best / worst"
                    value={`${profile!.consistency.best_game_z.toFixed(1)} / ${profile!.consistency.worst_game_z.toFixed(1)}`}
                  />
                </div>
              </Card>
            )}

            {profile!.lead_conversion && (
              <Card
                title="Lead conversion"
                subtitle="What happens after a gold lead at 15 minutes — and after a deficit."
              >
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Stat
                    label="Leads converted"
                    value={formatPercent(profile!.lead_conversion.lead_conversion_rate)}
                    hint={`${profile!.lead_conversion.leads_converted}/${profile!.lead_conversion.games_with_lead} games`}
                    tone={
                      profile!.lead_conversion.lead_conversion_rate !== null &&
                      profile!.lead_conversion.cohort_lead_conversion_rate !== null
                        ? profile!.lead_conversion.lead_conversion_rate >=
                          profile!.lead_conversion.cohort_lead_conversion_rate
                          ? "text-good"
                          : "text-warn"
                        : ""
                    }
                  />
                  <Stat
                    label="Cohort rate"
                    value={formatPercent(profile!.lead_conversion.cohort_lead_conversion_rate)}
                    hint="same rank band"
                  />
                  <Stat
                    label="Comebacks"
                    value={formatPercent(profile!.lead_conversion.comeback_rate)}
                    hint={`${profile!.lead_conversion.comebacks}/${profile!.lead_conversion.games_behind} games`}
                  />
                  <Stat
                    label="Games behind"
                    value={profile!.lead_conversion.games_behind}
                    hint="≥1k gold down at 15"
                  />
                </div>
              </Card>
            )}
          </div>

          {trend.length > 2 && (
            <Card
              title="Rolling form"
              subtitle="Five-game moving average, oldest game first"
            >
              <TrendChart
                data={trend}
                series={[
                  { key: "cs_per_min", label: "CS/min" },
                  { key: "vision_score_per_min", label: "Vision/min" },
                ]}
              />
            </Card>
          )}

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Roles">
              <div className="scroll-x">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th>Games</th>
                      <th>Win rate</th>
                      <th>Champions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profile!.role_splits.map((split) => (
                      <tr key={split.role}>
                        <td>{roleLabel(split.role)}</td>
                        <td className="stat">{split.games}</td>
                        <td className="stat">{formatPercent(split.win_rate)}</td>
                        <td className="text-ink-muted">{split.champions.join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="Champions">
              <div className="scroll-x">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Champion</th>
                      <th>Games</th>
                      <th>Win rate</th>
                      <th>KDA</th>
                      <th>CS/min</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profile!.champion_splits.map((split) => (
                      <tr key={split.champion_id}>
                        <td>{split.champion_name ?? split.champion_id}</td>
                        <td className="stat">{split.games}</td>
                        <td className="stat">{formatPercent(split.win_rate)}</td>
                        <td className="stat">{split.kda.toFixed(2)}</td>
                        <td className="stat">{split.cs_per_min.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <Card
            title="Recent matches"
            action={
              <Link
                href={`/player/${routeParams.platform}/${encodeURIComponent(riotId)}/matches`}
                className="link text-xs"
              >
                View all
              </Link>
            }
          >
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr>
                    <th>Result</th>
                    <th>Champion</th>
                    <th>Role</th>
                    <th>K/D/A</th>
                    <th>CS/min</th>
                    <th>GD@10</th>
                    <th>RCE</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {recent.map((match) => (
                    <tr key={match.match_id}>
                      <td className={match.win ? "text-good" : "text-bad"}>
                        {match.win ? "Win" : "Loss"}
                      </td>
                      <td>{match.champion_name ?? match.champion_id}</td>
                      <td className="text-ink-muted">{roleLabel(match.team_position)}</td>
                      <td className="stat">
                        {match.kills}/{match.deaths}/{match.assists}
                      </td>
                      <td className="stat">{match.cs_per_min?.toFixed(1) ?? "—"}</td>
                      <td className="stat">
                        {match.gold_diff_10 !== null
                          ? `${match.gold_diff_10 > 0 ? "+" : ""}${match.gold_diff_10.toFixed(0)}`
                          : "—"}
                      </td>
                      <td className="stat">{match.rce_raw?.toFixed(2) ?? "—"}</td>
                      <td>
                        <Link
                          href={`/match/${match.match_id}?puuid=${player.puuid}&platform=${routeParams.platform}&riotId=${encodeURIComponent(riotId)}`}
                          className="link text-xs"
                        >
                          Analyse
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
