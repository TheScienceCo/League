import { Card } from "@/components/ui";

export const metadata = { title: "Methodology" };

const SECTIONS = [
  {
    title: "Nothing here is a raw API field",
    body: [
      "Riot's match payload is stored faithfully, but it is an input, not the product. Every figure surfaced in the UI is a differential against the lane opponent, a rate, a share, a cohort percentile, or a model output.",
      "Where a value cannot be computed honestly it is left empty. A game that ended at minute nine has no gold difference at ten, and none is imputed.",
    ],
  },
  {
    title: "Cohorts, and why the comparison is per game",
    body: [
      "A number only means something relative to comparable circumstances, so every comparison controls for role, champion, rank band, patch and game length. Fully specifying all five gives the cleanest comparison and the emptiest cohorts, so a chain of progressively broader cohorts is materialised and the narrowest one with enough observations is used. When the fall-back happens, the UI says so.",
      "Comparisons are made per game, against that game's own cohort, and then summarised. Comparing a player's multi-game average against a distribution of single games is a units error: the mean of n games has a standard error of sigma over root n, so it drifts into the tails far too often and a merely below-average player reads as first percentile.",
    ],
  },
  {
    title: "Resource Conversion Efficiency",
    body: [
      "RCE is output share divided by resource share — champion damage share over team gold share. A player who takes 30% of their team's gold and produces 30% of its damage scores 1.0 regardless of how long the game ran or how far ahead the team was, because both sides of the ratio are shares.",
      "It does not control for champion: a marksman converts gold into damage far better than an enchanter, and that is a property of the pick, not the player. The normalised form is a z-score against the narrowest available champion, role, rank and patch cohort, which removes exactly that.",
    ],
  },
  {
    title: "Map risk",
    body: [
      "Every timeline frame is an exposure — a player at a position, at a time, in a game state — labelled with whether they died within the next thirty seconds. Aggregating over a grid gives an empirical risk surface; a gradient-boosted classifier over the same exposures with richer features gives the per-player figures.",
      "The model is deliberately restricted to information the player could legitimately have had: their own position, their own team's economy, the clock, the objective state, and events announced to everyone. It is never given live enemy positions, even though the historical timeline contains them. That is partly principle and partly a useful property — a model that never needed hidden information cannot leak it.",
      "Risk-adjusted deaths are actual deaths minus the deaths the model expected given where and when the player stood. A positive figure points at what happened in those spots, not at the spots themselves.",
    ],
  },
  {
    title: "Roam value",
    body: [
      "A roam is detected as consecutive minutes in which a laner is far from their lane centre-line. Timeline frames arrive once per minute, so a sub-thirty-second collapse is invisible; this is a real resolution limit, not a modelling choice.",
      "Valuation compares what the roam produced against what the player would have gained by staying — using that same player's own median in-lane gold and XP rate in that same game as the baseline, which controls for champion, patch and game state simultaneously. Objective credit is added and a fixed cost per death subtracted. The gold conversions are reasonable constants, not fitted values.",
    ],
  },
  {
    title: "Skill Gap Analysis",
    body: [
      "The question is which measurable behaviours separate rank bands after controlling for what a player picks and when they played. Nothing is hard-coded about what good looks like.",
      "Each feature is centred on its champion, role, patch and duration control group, with group means shrunk toward broader means in proportion to how little data the group has. A gradient-boosted classifier then predicts rank band from those residuals, cross-validated with GroupKFold on player id so no player appears in both folds — without that the model memorises players rather than behaviours and every score is inflated.",
      "The headline metric is the Spearman correlation between the true band and the model's probability-weighted expected band. The target is ordinal, so being one band out is a different kind of error from being four out, and argmax accuracy cannot express that. Classes are balanced, so the reference point is a fixed one-over-k rather than the majority share.",
      "Behaviours are ranked by permutation importance multiplied by how far behind the player is, so a behaviour surfaces only when it both separates ranks and is one this player is actually behind on.",
    ],
  },
  {
    title: "Decision Value Added (experimental)",
    body: [
      "DVA compares the win-probability change that actually followed a moment against what usually follows historically similar moments, found by nearest neighbours over state vectors drawn from other matches.",
      "The attribution step is the weak link and is deliberately conservative: win probability is a property of ten players, so a player is credited with only the share of the residual their own involvement in the window supports. That is a heuristic, not an identification strategy. The whole feature is labelled experimental, is excluded from the Skill Gap feature set, and its numbers should be read directionally.",
    ],
  },
  {
    title: "What this cannot tell you",
    body: [
      "All of it is observational. A behaviour that separates ranks may do so because it causes better outcomes, because better players happen to do it, or because both share a cause this data cannot see. No claim of causation is made anywhere, and the phrasing throughout — 'associated with', never 'because' — reflects that.",
      "Comparisons also cannot see team quality, matchup, communication, or the state a player was in. Those are large and unmeasured.",
    ],
  },
  {
    title: "Data and compliance",
    body: [
      "Only data legitimately available through the public Riot API and match history is used, and all analysis is retrospective. There is no live-game or spectator integration, no automation of gameplay, and nothing surfaced that a player could not have known at the time.",
      "Without an API key the application serves a deterministic simulator in the same payload shape, so the whole pipeline is runnable and testable without credentials. Simulated matches are clearly a data generator: nothing learned from them says anything about real players.",
    ],
  },
];

export default function MethodologyPage() {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Methodology</h1>
        <p className="mt-2 max-w-3xl text-ink-muted">
          How each number on this site is produced, and what it does and does not
          support.
        </p>
      </header>
      {SECTIONS.map((section) => (
        <Card key={section.title} title={section.title}>
          <div className="space-y-3">
            {section.body.map((paragraph, i) => (
              <p key={i} className="max-w-3xl text-sm leading-relaxed text-ink-muted">
                {paragraph}
              </p>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
