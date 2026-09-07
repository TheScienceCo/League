import Link from "next/link";

import { HorizontalBars } from "@/components/charts";
import { Card, Disclaimer, EmptyState, PercentileBar, PlayerTabs } from "@/components/ui";
import { api } from "@/lib/api";
import {
  effectivePercentile,
  formatMetric,
  ordinal,
  percentileTone,
  TIER_GROUPS,
  tierLabel,
} from "@/lib/format";
import type { CohortTable } from "@/lib/types";

import { PlayerHeader } from "../player-header";
import { resolvePlayer, type PlayerRouteParams } from "../player-data";

export const dynamic = "force-dynamic";

export default async function ComparePage({
  params,
  searchParams,
}: {
  params: Promise<PlayerRouteParams>;
  searchParams: Promise<{ target?: string }>;
}) {
  const routeParams = await params;
  const { target } = await searchParams;
  const { player, riotId } = await resolvePlayer(routeParams);

  let table: CohortTable | null = null;
  let profile = null;
  try {
    [table, profile] = await Promise.all([
      api.cohort(player.puuid, target),
      api.profile(player.puuid).catch(() => null),
    ]);
  } catch {
    table = null;
  }

  const base = `/player/${routeParams.platform}/${encodeURIComponent(riotId)}/compare`;
  const gapRows = (table?.rows ?? [])
    .filter((row) => row.gap_z !== null)
    .slice(0, 12)
    .map((row) => ({ label: row.label, value: Number(row.gap_z) }));

  return (
    <div>
      <PlayerHeader
        player={player}
        riotId={riotId}
        platform={routeParams.platform}
        profile={profile}
      />
      <PlayerTabs platform={routeParams.platform} riotId={riotId} active="compare" />

      {!table ? (
        <EmptyState title="Nothing to compare yet">
          Ingest matches to build a cohort comparison.
        </EmptyState>
      ) : (
        <div className="space-y-5">
          <Card
            title="Compare against a rank band"
            subtitle={`Currently comparing ${tierLabel(table.player_tier_group)} against ${tierLabel(table.target_tier_group)}, holding role, champion, patch and game length constant.`}
          >
            <div className="flex flex-wrap gap-2">
              {TIER_GROUPS.map((band) => (
                <Link
                  key={band}
                  href={`${base}?target=${band}`}
                  className={`rounded border px-2.5 py-1 text-xs ${
                    band === table.target_tier_group
                      ? "border-accent bg-accent/15 text-accent"
                      : "border-surface-border text-ink-muted hover:border-accent"
                  }`}
                >
                  {tierLabel(band)}
                </Link>
              ))}
            </div>
          </Card>

          {gapRows.length > 0 && (
            <Card
              title={`Largest gaps to ${tierLabel(table.target_tier_group)}`}
              subtitle="In standard deviations. Red bars are behaviours the target band does better; green are ones this player already leads on."
            >
              <HorizontalBars
                data={gapRows}
                height={Math.max(240, gapRows.length * 26)}
                diverging
                format="sigma"
              />
            </Card>
          )}

          <Card title="Full comparison">
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Player</th>
                    <th>Own band median</th>
                    <th>{tierLabel(table.target_tier_group)} mean</th>
                    <th>Gap</th>
                    <th>Percentile in own band</th>
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row) => {
                    const effective = effectivePercentile(
                      row.player_percentile,
                      row.higher_is_better,
                    );
                    return (
                      <tr key={row.metric}>
                        <td>{row.label}</td>
                        <td className="stat">{formatMetric(row.metric, row.player_value)}</td>
                        <td className="stat text-ink-muted">
                          {formatMetric(row.metric, row.own_cohort_median)}
                        </td>
                        <td className="stat text-ink-muted">
                          {formatMetric(row.metric, row.target_cohort_mean)}
                        </td>
                        <td
                          className={`stat ${
                            (row.gap_z ?? 0) > 0.3
                              ? "text-bad"
                              : (row.gap_z ?? 0) < -0.3
                                ? "text-good"
                                : ""
                          }`}
                        >
                          {row.gap_z !== null
                            ? `${row.gap_z > 0 ? "+" : ""}${row.gap_z.toFixed(2)}σ`
                            : "—"}
                        </td>
                        <td className="w-32">
                          <div className="flex items-center gap-2">
                            <PercentileBar value={effective} />
                            <span
                              className={`w-10 shrink-0 text-right text-xs ${percentileTone(effective)}`}
                            >
                              {effective !== null ? ordinal(effective) : "—"}
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Disclaimer>
              A positive gap means the target band performs better on that
              behaviour. Gaps are descriptive: they compare groups of players, and
              do not establish that closing one would move this player between
              bands.
            </Disclaimer>
          </Card>
        </div>
      )}
    </div>
  );
}
