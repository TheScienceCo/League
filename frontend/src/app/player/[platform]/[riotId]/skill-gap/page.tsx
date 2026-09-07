import { Card, Disclaimer, EmptyState, PercentileBar, PlayerTabs, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import {
  effectivePercentile,
  formatMetric,
  ordinal,
  percentileTone,
  tierLabel,
} from "@/lib/format";
import type { SkillGapReport } from "@/lib/types";

import { PlayerHeader } from "../player-header";
import { resolvePlayer, type PlayerRouteParams } from "../player-data";

export const dynamic = "force-dynamic";

export default async function SkillGapPage({
  params,
  searchParams,
}: {
  params: Promise<PlayerRouteParams>;
  searchParams: Promise<{ target?: string }>;
}) {
  const routeParams = await params;
  const { target } = await searchParams;
  const { player, riotId } = await resolvePlayer(routeParams);

  let report: SkillGapReport | null = null;
  let error: string | null = null;
  let profile = null;
  try {
    [report, profile] = await Promise.all([
      api.skillGap(player.puuid, target, 5),
      api.profile(player.puuid).catch(() => null),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Could not build the skill gap report";
  }

  const metrics = report?.model.metrics ?? {};

  return (
    <div>
      <PlayerHeader
        player={player}
        riotId={riotId}
        platform={routeParams.platform}
        profile={profile}
      />
      <PlayerTabs platform={routeParams.platform} riotId={riotId} active="skill-gap" />

      {!report ? (
        <EmptyState title="Skill gap analysis unavailable">
          {error ??
            "The rank-separation model needs a corpus spanning several rank bands."}
        </EmptyState>
      ) : (
        <div className="space-y-5">
          <Card
            title={`Behaviours separating this player from ${tierLabel(report.target_tier_group)}`}
            subtitle={`Ranked by the model's weight on each behaviour multiplied by how far behind the player is. Based on ${report.games_analyzed} analysed games.`}
          >
            <ol className="space-y-4">
              {report.behaviours.map((behaviour, index) => {
                const effective = effectivePercentile(
                  behaviour.player_percentile,
                  behaviour.higher_is_better,
                );
                return (
                  <li key={behaviour.feature} className="flex gap-4">
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/15 text-sm font-semibold text-accent">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <h3 className="font-medium">{behaviour.label}</h3>
                        <span className="text-xs text-ink-faint">
                          gap {behaviour.gap_z.toFixed(2)}σ · model weight{" "}
                          {(behaviour.importance * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div className="mt-1.5 grid gap-3 text-sm sm:grid-cols-3">
                        <div>
                          <span className="label">This player</span>
                          <div className="stat">
                            {formatMetric(behaviour.feature, behaviour.player_value)}
                          </div>
                        </div>
                        <div>
                          <span className="label">
                            Gap to {tierLabel(report.target_tier_group)}
                          </span>
                          <div
                            className={`stat ${behaviour.gap_z > 0 ? "text-warn" : "text-good"}`}
                          >
                            {behaviour.gap_z > 0 ? "+" : ""}
                            {formatMetric(behaviour.feature, behaviour.gap_natural)}
                          </div>
                          {behaviour.target_band_average !== null && (
                            <div className="mt-0.5 text-xs text-ink-faint">
                              band average{" "}
                              {formatMetric(behaviour.feature, behaviour.target_band_average)}{" "}
                              (uncontrolled)
                            </div>
                          )}
                        </div>
                        <div>
                          <span className="label">Own cohort percentile</span>
                          <div className="flex items-center gap-2">
                            <PercentileBar value={effective} />
                            <span className={`text-xs ${percentileTone(effective)}`}>
                              {effective !== null ? ordinal(effective) : "—"}
                            </span>
                          </div>
                        </div>
                      </div>
                      <p className="mt-1.5 text-xs text-ink-faint">
                        The gap is measured after controlling for champion, role,
                        patch and game length, so it can differ in sign from a raw
                        band average when this player&rsquo;s mix differs from the
                        band&rsquo;s. Univariate correlation with rank:{" "}
                        {behaviour.rank_correlation >= 0 ? "+" : ""}
                        {behaviour.rank_correlation.toFixed(2)}
                        {" · "}
                        {behaviour.higher_is_better ? "higher is better" : "lower is better"}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card
              title="Model quality"
              subtitle="Cross-validated with players never split across folds."
            >
              <div className="grid grid-cols-2 gap-4">
                <Stat
                  label="Rank ordering (Spearman)"
                  value={
                    typeof metrics.cv_rank_spearman === "number"
                      ? metrics.cv_rank_spearman.toFixed(3)
                      : "—"
                  }
                  hint="1.0 = perfect ordering"
                />
                <Stat
                  label="Balanced accuracy"
                  value={
                    typeof metrics.cv_balanced_accuracy === "number"
                      ? metrics.cv_balanced_accuracy.toFixed(3)
                      : "—"
                  }
                  hint={
                    typeof metrics.chance_balanced_accuracy === "number"
                      ? `chance = ${metrics.chance_balanced_accuracy.toFixed(2)}`
                      : undefined
                  }
                />
                <Stat
                  label="Training rows"
                  value={
                    typeof metrics.n_rows === "number" ? metrics.n_rows.toLocaleString() : "—"
                  }
                  hint={
                    typeof metrics.n_players === "number"
                      ? `${metrics.n_players.toLocaleString()} players`
                      : undefined
                  }
                />
                <Stat
                  label="Rank bands"
                  value={typeof metrics.n_tier_bands === "number" ? metrics.n_tier_bands : "—"}
                  hint={report.model.version ? `v${report.model.version}` : undefined}
                />
              </div>
              <Disclaimer>
                The headline number is rank ordering, not accuracy: the target is
                ordinal, so being one band out is a different kind of error from
                being four out, and argmax accuracy cannot express that.
              </Disclaimer>
            </Card>

            <Card title="How to read this">
              <ul className="space-y-2 text-sm text-ink-muted">
                <li>
                  <strong className="text-ink">Nothing here is hard-coded.</strong> The
                  ranking of behaviours comes from permutation importance in a model
                  trained to separate rank bands, not from an opinion about what
                  matters.
                </li>
                <li>
                  <strong className="text-ink">Controls first.</strong> Every behaviour
                  is centred on its champion × role × patch × duration group before the
                  model sees it, so it cannot learn champion identity and call it skill.
                </li>
                <li>
                  <strong className="text-ink">Gaps are in σ.</strong> A gap of 1.0
                  means the target band is one standard deviation better on that
                  behaviour, after those controls.
                </li>
              </ul>
              <ul className="mt-4 space-y-1.5 text-xs text-ink-faint">
                {report.caveats.map((caveat) => (
                  <li key={caveat}>• {caveat}</li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
