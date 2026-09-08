import Link from "next/link";
import { Card } from "@/components/ui";

export const metadata = {
  title: "AoE2 Analytics — Replay analysis & coaching",
  description: "Upload replays to analyze economy, military, scouting, and strategy with peer comparison and coaching insights.",
};

const FEATURES = [
  {
    title: "Economy Analysis",
    description: "TC idle time, resource float, villager production, and collection rates with peer comparison",
  },
  {
    title: "Military Efficiency",
    description: "Resources killed/lost, engagement efficiency, unit composition, and production uptime",
  },
  {
    title: "Strategic Timing",
    description: "Age-ups, expansions, reactions, and decision quality compared to high-Elo peers",
  },
  {
    title: "Scouting & Information",
    description: "Map coverage, discovery timing, and information advantage estimation",
  },
  {
    title: "Skill Gap Analysis",
    description: "ML-identified behaviors separating Elo tiers with percentile rankings",
  },
  {
    title: "Coaching Report",
    description: "Strengths, mistakes, expensive decisions, and actionable improvements",
  },
];

export default function AoE2LandingPage() {
  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <section className="space-y-6 py-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            AoE2 Analytics
          </h1>
          <p className="mt-4 text-xl text-ink-muted">
            Analyze your Age of Empires II replays to quantify RTS skill and identify improvement opportunities.
          </p>
        </div>

        <div className="flex gap-4">
          <Link
            href="/aoe2/upload"
            className="rounded-lg bg-accent px-6 py-3 font-medium text-white hover:bg-accent-dark transition"
          >
            Upload Replay
          </Link>
          <Link
            href="/aoe2/methodology"
            className="rounded-lg border border-surface-border px-6 py-3 font-medium hover:bg-surface-raised transition"
          >
            Learn More
          </Link>
        </div>
      </section>

      {/* Features Grid */}
      <section className="space-y-6">
        <h2 className="text-2xl font-bold">What You Get</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className="rounded-lg border border-surface-border bg-surface-raised p-4"
            >
              <h3 className="font-semibold">{feature.title}</h3>
              <p className="mt-2 text-sm text-ink-muted">{feature.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section className="space-y-6">
        <h2 className="text-2xl font-bold">How It Works</h2>
        <ol className="space-y-4">
          <li className="flex gap-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-bold text-white">
              1
            </span>
            <div>
              <h3 className="font-semibold">Upload a replay file</h3>
              <p className="text-sm text-ink-muted">
                Drag and drop your .aoe2record file or use the browser uploader
              </p>
            </div>
          </li>
          <li className="flex gap-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-bold text-white">
              2
            </span>
            <div>
              <h3 className="font-semibold">Replay parsing & analysis</h3>
              <p className="text-sm text-ink-muted">
                Extract events, reconstruct game state, and calculate metrics
              </p>
            </div>
          </li>
          <li className="flex gap-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-bold text-white">
              3
            </span>
            <div>
              <h3 className="font-semibold">Compare against peers</h3>
              <p className="text-sm text-ink-muted">
                See percentile ranks and peer medians for your Elo band and civilization
              </p>
            </div>
          </li>
          <li className="flex gap-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-bold text-white">
              4
            </span>
            <div>
              <h3 className="font-semibold">Get coaching insights</h3>
              <p className="text-sm text-ink-muted">
                Actionable recommendations to improve economy, military, and strategy
              </p>
            </div>
          </li>
        </ol>
      </section>

      {/* Metrics Section */}
      <section className="space-y-6">
        <h2 className="text-2xl font-bold">Core Metrics</h2>
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <h3 className="font-semibold">Economy</h3>
            <ul className="space-y-1 text-sm text-ink-muted">
              <li>• TC idle time (milliseconds)</li>
              <li>• Resource float (unspent resources)</li>
              <li>• Villager production uptime</li>
              <li>• Collection rates by resource</li>
            </ul>
          </div>
          <div className="space-y-2">
            <h3 className="font-semibold">Military</h3>
            <ul className="space-y-1 text-sm text-ink-muted">
              <li>• Resources killed/lost ratio</li>
              <li>• Engagement efficiency</li>
              <li>• Production uptime</li>
              <li>• Unit composition evolution</li>
            </ul>
          </div>
          <div className="space-y-2">
            <h3 className="font-semibold">Strategic</h3>
            <ul className="space-y-1 text-sm text-ink-muted">
              <li>• Age-up timing comparisons</li>
              <li>• Reaction latency to opponents</li>
              <li>• Tempo score</li>
              <li>• First aggression timing</li>
            </ul>
          </div>
          <div className="space-y-2">
            <h3 className="font-semibold">Scouting</h3>
            <ul className="space-y-1 text-ink-muted text-sm">
              <li>• Map coverage percentage</li>
              <li>• Time to discover enemy</li>
              <li>• Scout efficiency</li>
              <li>• Information advantage</li>
            </ul>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="space-y-4 rounded-lg border border-surface-border bg-surface-raised p-8 text-center">
        <h2 className="text-2xl font-bold">Ready to analyze your replays?</h2>
        <p className="text-ink-muted">
          Start with a single replay upload to see how the platform works.
        </p>
        <Link
          href="/aoe2/upload"
          className="inline-block rounded-lg bg-accent px-8 py-3 font-medium text-white hover:bg-accent-dark transition"
        >
          Upload Your First Replay
        </Link>
      </section>

      {/* Methodology Note */}
      <section className="space-y-4 rounded-lg border border-surface-border/50 bg-surface-raised/50 p-6 text-sm text-ink-muted">
        <h3 className="font-semibold text-ink">Important</h3>
        <p>
          All analysis is retrospective and based on replay data that players can already access.
          Model-derived figures (ML estimates) describe statistical association, not causation.
          See <Link href="/aoe2/methodology" className="text-accent hover:underline">methodology</Link> for details.
        </p>
      </section>
    </div>
  );
}
