import { HorizontalBars, TierMeansChart } from "@/components/charts";
import { Card, Disclaimer, EmptyState, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { formatMetric, tierLabel } from "@/lib/format";
import type { RankSeparation } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Rank separation" };

const TIER_ORDER = ["IRON_BRONZE", "SILVER_GOLD", "PLAT_EMERALD", "DIAMOND", "MASTER_PLUS"];

export default async function InsightsPage() {
  let data: RankSeparation | null = null;
  let error: string | null = null;
  try {
    data = await api.rankSeparation(15);
  } catch (e) {
    error = e instanceof Error ? e.message : "Could not load the model";
  }

  if (!data) {
    return (
      <EmptyState title="Rank-separation model not trained">
        {error ??
          "Seed a corpus spanning several rank bands, then run the analytics refresh."}
      </EmptyState>
    );
  }

  const metrics = data.model.metrics ?? {};
  const importanceRows = data.behaviours.map((b) => ({
    label: b.label,
    value: b.importance,
  }));
  const top = data.behaviours.slice(0, 4);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          What actually separates rank bands
        </h1>
        <p className="mt-2 max-w-3xl text-ink-muted">
          A model is trained to predict a player’s rank band from their measured
          behaviour, after every feature has been centred on its champion, role,
          patch and game-length control group. The behaviours it relies on most are
          shown below. Nothing in this list was chosen by hand.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <Stat
            label="Rank ordering (Spearman)"
            value={
              typeof metrics.cv_rank_spearman === "number"
                ? metrics.cv_rank_spearman.toFixed(3)
                : "—"
            }
            hint="cross-validated, players not split"
          />
        </Card>
        <Card>
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
        </Card>
        <Card>
          <Stat
            label="Training rows"
            value={typeof metrics.n_rows === "number" ? metrics.n_rows.toLocaleString() : "—"}
            hint={
              typeof metrics.n_players === "number"
                ? `${metrics.n_players.toLocaleString()} players`
                : undefined
            }
          />
        </Card>
        <Card>
          <Stat
            label="Model version"
            value={data.model.version ?? "—"}
            hint={
              typeof metrics.median_games_per_player === "number"
                ? `median ${metrics.median_games_per_player} game(s)/player`
                : undefined
            }
          />
        </Card>
      </div>

      <Card
        title="Behaviour importance"
        subtitle="Permutation importance on a held-out, player-disjoint split. Higher means the model's ability to place a player degrades more when this behaviour is shuffled."
      >
        <HorizontalBars
          data={importanceRows}
          height={Math.max(300, importanceRows.length * 26)}
          format="percent"
        />
        <Disclaimer>
          Importance is multivariate: a behaviour can rank low because it carries
          little information, or because another feature already carries it. The
          univariate correlation column in the table below separates those cases.
        </Disclaimer>
      </Card>

      <div className="grid gap-5 sm:grid-cols-2">
        {top.map((behaviour) => {
          const chartData = TIER_ORDER.filter(
            (tier) => behaviour.tier_means[tier] !== undefined,
          ).map((tier) => ({
            tier: tierLabel(tier),
            value: behaviour.tier_means[tier] ?? null,
          }));
          return (
            <Card
              key={behaviour.feature}
              title={behaviour.label}
              subtitle={`Mean by rank band · ${behaviour.higher_is_better ? "higher is better" : "lower is better"}`}
            >
              <TierMeansChart data={chartData} />
            </Card>
          );
        })}
      </div>

      <Card title="All behaviours">
        <div className="scroll-x">
          <table className="data">
            <thead>
              <tr>
                <th>Behaviour</th>
                <th>Model importance</th>
                <th>Correlation with rank</th>
                <th>Direction</th>
                {TIER_ORDER.map((tier) => (
                  <th key={tier}>{tierLabel(tier)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.behaviours.map((behaviour) => (
                <tr key={behaviour.feature}>
                  <td>{behaviour.label}</td>
                  <td className="stat">{(behaviour.importance * 100).toFixed(1)}%</td>
                  <td className="stat">
                    {behaviour.rank_correlation >= 0 ? "+" : ""}
                    {behaviour.rank_correlation.toFixed(2)}
                  </td>
                  <td className="text-xs text-ink-muted">
                    {behaviour.higher_is_better ? "higher better" : "lower better"}
                  </td>
                  {TIER_ORDER.map((tier) => (
                    <td key={tier} className="stat text-ink-muted">
                      {formatMetric(behaviour.feature, behaviour.tier_means[tier] ?? null)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Disclaimer>
          These are associations within the ingested dataset. Higher-ranked players
          differ from lower-ranked players in many ways at once, and this analysis
          cannot separate a behaviour that raises rank from one that merely
          accompanies it.
        </Disclaimer>
      </Card>
    </div>
  );
}
