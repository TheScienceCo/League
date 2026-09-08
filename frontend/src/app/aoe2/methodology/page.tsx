export const metadata = {
  title: "Methodology",
  description: "How AoE2 Analytics calculates metrics, derives insights, and ensures reproducibility.",
};

export default function MethodologyPage() {
  return (
    <div className="space-y-8 py-8 max-w-3xl">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold">Methodology</h1>
        <p className="text-ink-muted">
          How we derive metrics from replays and provide actionable coaching insights
        </p>
      </div>

      {/* Overview */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Overview</h2>
        <p className="text-ink-muted">
          AoE2 Analytics reconstructs complete game state from replay command streams and derives
          comprehensive metrics to quantify player skill. All analysis is retrospective and based
          on data that players can already access.
        </p>
      </section>

      {/* Data Processing Pipeline */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Processing Pipeline</h2>
        <div className="space-y-3">
          <div>
            <h3 className="font-semibold">1. Replay Parsing</h3>
            <p className="text-sm text-ink-muted">
              Extract action IDs, timestamps, and player information from the .aoe2record file.
              The parser reconstructs the command stream that was sent to the game engine.
            </p>
          </div>
          <div>
            <h3 className="font-semibold">2. Event Normalization</h3>
            <p className="text-sm text-ink-muted">
              Convert raw replay events into standardized event types: AGE_UP, BUILD_COMPLETED,
              UNIT_CREATED, UNIT_DIED, TECHNOLOGY_RESEARCHED, etc.
            </p>
          </div>
          <div>
            <h3 className="font-semibold">3. State Reconstruction</h3>
            <p className="text-sm text-ink-muted">
              Process events chronologically to rebuild game state. Create snapshots every 5-15
              seconds containing: resources, population, buildings, units, technologies, army value.
            </p>
          </div>
          <div>
            <h3 className="font-semibold">4. Metrics Calculation</h3>
            <p className="text-sm text-ink-muted">
              Analyze state snapshots and events to derive 30+ metrics across economy, military,
              scouting, and strategic dimensions.
            </p>
          </div>
          <div>
            <h3 className="font-semibold">5. Peer Comparison</h3>
            <p className="text-sm text-ink-muted">
              Compare player metrics against historical cohorts stratified by Elo band, civilization,
              and map type. Generate percentile ranks (0-100).
            </p>
          </div>
          <div>
            <h3 className="font-semibold">6. Coaching Report</h3>
            <p className="text-sm text-ink-muted">
              Identify strengths, mistakes, and expensive decisions. Generate actionable
              recommendations tied to quantified events.
            </p>
          </div>
        </div>
      </section>

      {/* Metric Definitions */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Metric Definitions</h2>

        <div className="space-y-4">
          <div className="rounded-lg border border-surface-border p-4">
            <h3 className="font-semibold">Economy Metrics</h3>
            <dl className="mt-3 space-y-2 text-sm text-ink-muted">
              <div>
                <dt className="font-medium text-ink">TC Idle Time</dt>
                <dd>Milliseconds Town Center spends not producing a villager after Feudal Age.</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Resource Float</dt>
                <dd>Sum of unspent resources at any point in time. Peak and average values tracked.</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Villager Production Uptime</dt>
                <dd>Percentage of time TC produces villagers when food is available (0-100%).</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Resource Collection Rates</dt>
                <dd>Resources/minute by type (food, wood, gold, stone). Derived from state snapshots.</dd>
              </div>
            </dl>
          </div>

          <div className="rounded-lg border border-surface-border p-4">
            <h3 className="font-semibold">Military Metrics</h3>
            <dl className="mt-3 space-y-2 text-sm text-ink-muted">
              <div>
                <dt className="font-medium text-ink">Resources Killed/Lost</dt>
                <dd>Total unit value destroyed or lost in combat. Value estimated by unit type.</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Engagement Efficiency</dt>
                <dd>Kill-to-loss resource ratio, normalized to 0-100 scale (1:1 ratio = 50).</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Military Production Uptime</dt>
                <dd>Percentage of time production buildings (Range, Stable, Barracks) are active.</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Unit Composition</dt>
                <dd>Count and type distribution of units over time. Reflects strategy choices.</dd>
              </div>
            </dl>
          </div>

          <div className="rounded-lg border border-surface-border p-4">
            <h3 className="font-semibold">Strategic Metrics</h3>
            <dl className="mt-3 space-y-2 text-sm text-ink-muted">
              <div>
                <dt className="font-medium text-ink">Age-Up Timing</dt>
                <dd>Game time (seconds) when advancing to Feudal, Castle, Imperial. Compared to peer medians.</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Reaction Latency</dt>
                <dd>Delay between opponent action (military building) and counter-response.</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Tempo Score</dt>
                <dd>Composite of resource spending rate and army activity. Higher = faster pace.</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">First Aggression</dt>
                <dd>Game time when first military unit or offensive building appears.</dd>
              </div>
            </dl>
          </div>

          <div className="rounded-lg border border-surface-border p-4">
            <h3 className="font-semibold">Scouting Metrics</h3>
            <dl className="mt-3 space-y-2 text-sm text-ink-muted">
              <div>
                <dt className="font-medium text-ink">Scouting Coverage</dt>
                <dd>Estimated percentage of map explored, inferred from scout unit movements.</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Time to Enemy Discovery</dt>
                <dd>Game time when first enemy unit or building is spotted.</dd>
              </div>
              <div>
                <dt className="font-medium text-ink">Scout Efficiency</dt>
                <dd>Information value per scout unit active. Higher = better scouting.</dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

      {/* Peer Comparison */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Peer Comparison Methodology</h2>
        <p className="text-sm text-ink-muted">
          Metrics are compared against historical cohorts to provide context. Cohorts are stratified by:
        </p>
        <ul className="list-disc list-inside space-y-1 text-sm text-ink-muted">
          <li><strong>Elo Band:</strong> 1000–1200, 1200–1400, ..., 2000+</li>
          <li><strong>Civilization:</strong> Separate baselines for each civ due to balance differences</li>
          <li><strong>Map Type:</strong> Arabia, Nomad, and other map types have different patterns</li>
          <li><strong>Game Length:</strong> Early aggression vs. late-game macro plays occur in different timeframes</li>
        </ul>
        <p className="text-sm text-ink-muted mt-3">
          Your percentile rank indicates how you compare: 50th percentile = median, 75th = top 25%,
          10th = bottom 10%.
        </p>
      </section>

      {/* Reconstructed vs. Estimated */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Data Reliability</h2>
        <div className="space-y-3">
          <div className="rounded-lg border border-green-200 bg-green-50 p-4 dark:border-green-800 dark:bg-green-900/20">
            <h3 className="font-semibold text-green-900 dark:text-green-200">Directly Observed</h3>
            <p className="text-sm text-green-800 dark:text-green-300 mt-1">
              Parsed directly from replay events. Examples: unit creation/death, building construction,
              age advances, technology research.
            </p>
          </div>

          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
            <h3 className="font-semibold text-blue-900 dark:text-blue-200">Reconstructed</h3>
            <p className="text-sm text-blue-800 dark:text-blue-300 mt-1">
              Estimated from event stream with documented assumptions. Examples: resource float,
              villager idle time, TC idle time. Estimates may have ±5-10% margin of error.
            </p>
          </div>

          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
            <h3 className="font-semibold text-amber-900 dark:text-amber-200">ML-Estimated</h3>
            <p className="text-sm text-amber-800 dark:text-amber-300 mt-1">
              Model-derived metrics describing association within historical data. Examples:
              skill gap dimensions, win probability, player archetypes. Marked as estimates with
              confidence intervals.
            </p>
          </div>
        </div>
      </section>

      {/* Important Caveats */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Important Caveats</h2>
        <ul className="space-y-2 text-sm text-ink-muted list-disc list-inside">
          <li>
            <strong>Fog of war:</strong> We cannot see enemy villager positions or hidden units, so some estimates
            are inferred.
          </li>
          <li>
            <strong>Villager assignments:</strong> We estimate villager distribution from production building
            placement and efficiency.
          </li>
          <li>
            <strong>Map variability:</strong> Custom maps lack robust peer cohorts. Statistics are most reliable
            on standard maps (Arabia, Nomad).
          </li>
          <li>
            <strong>Patch differences:</strong> Game balance changes across patches affect comparisons.
            Metrics track patch version for reproducibility.
          </li>
          <li>
            <strong>Correlation ≠ Causation:</strong> High TC idle time correlates with lower Elo, but idling
            TC is a symptom, not the root cause.
          </li>
        </ul>
      </section>

      {/* Reproducibility */}
      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Reproducibility</h2>
        <p className="text-sm text-ink-muted">
          All metrics are deterministic: the same replay file always produces identical metrics.
          Metrics are versioned so that improvements to the calculation method don't invalidate
          historical data—we can recompute old games with new algorithms while preserving the
          version history.
        </p>
      </section>

      {/* More Info */}
      <section className="rounded-lg border border-surface-border/50 bg-surface-raised/50 p-4 text-sm text-ink-muted">
        <p>
          For questions about methodology or to report issues, see the{" "}
          <a
            href="https://github.com/thescienceco/league"
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline"
          >
            GitHub repository
          </a>
          .
        </p>
      </section>
    </div>
  );
}
