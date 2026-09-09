import Link from "next/link";

export const metadata = {
  title: "AoE2 Analytics — replay analysis",
  description:
    "Upload an Age of Empires II replay and get age timings, a banked-resource curve, build order and quantified observations.",
};

/** What the parser can actually recover from a replay file today. */
const WORKS = [
  {
    title: "Age timings",
    body: "Feudal, Castle and Imperial to the second, plus the gap to your opponent. Read from the game's own age transitions, so these are exact.",
    tag: "observed",
  },
  {
    title: "Banked resources over time",
    body: "A curve of everything sitting unspent, and which age you were least efficient in. Combined across all four resources — the per-type split is not transmitted.",
    tag: "inferred",
  },
  {
    title: "Build order",
    body: "Every building you placed, when and where, and the opening that implies.",
    tag: "observed",
  },
  {
    title: "Production gaps",
    body: "The longest stretch you went without queuing a villager — a proxy for an idle Town Center.",
    tag: "reconstructed",
  },
  {
    title: "Effective APM",
    body: "Meaningful commands per minute, with duplicate and spam orders excluded.",
    tag: "observed",
  },
  {
    title: "Quantified observations",
    body: "Plain-language notes, each tied to a number that was actually measured. No generic advice.",
    tag: "derived",
  },
];

const TAG_STYLE: Record<string, string> = {
  observed: "bg-emerald-500/15 text-emerald-500",
  inferred: "bg-amber-500/15 text-amber-500",
  reconstructed: "bg-sky-500/15 text-sky-500",
  derived: "bg-violet-500/15 text-violet-400",
};

export default function LandingPage() {
  return (
    <div className="space-y-14 py-8">
      <section className="space-y-5">
        <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
          What your replay can actually tell you
        </h1>
        <p className="max-w-2xl text-lg text-ink-muted">
          Drop in an <code className="font-mono text-base">.aoe2record</code> file and get
          your age timings against your opponent&rsquo;s, a curve of everything you left
          unspent, and your build order — each figure labelled with how it was obtained.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/upload"
            className="rounded-lg bg-accent px-6 py-3 font-medium text-white transition hover:opacity-90"
          >
            Analyse a replay
          </Link>
          <Link
            href="/methodology"
            className="rounded-lg border border-surface-border px-6 py-3 font-medium transition hover:bg-surface-raised"
          >
            How it works
          </Link>
        </div>
      </section>

      <section className="space-y-5">
        <h2 className="text-2xl font-semibold">What you get</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {WORKS.map((f) => (
            <div
              key={f.title}
              className="space-y-2 rounded-lg border border-surface-border bg-surface-raised p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold">{f.title}</h3>
                <span
                  className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${TAG_STYLE[f.tag]}`}
                >
                  {f.tag}
                </span>
              </div>
              <p className="text-sm text-ink-muted">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-surface-border bg-surface-raised/50 p-6">
        <h2 className="text-2xl font-semibold">What a replay cannot tell you</h2>
        <p className="max-w-3xl text-ink-muted">
          A replay is a <strong>command stream</strong>: it records the inputs players sent
          to the engine, not the outcomes the engine produced. Your build orders and age
          advances are in there. Unit deaths, kills, and combat results are{" "}
          <strong>not in the file at all</strong>.
        </p>
        <p className="max-w-3xl text-ink-muted">
          So there is no kill/death ratio here, and no &ldquo;resources destroyed&rdquo;
          figure. Rather than estimate them and present the guess as a measurement, those
          metrics report <span className="font-mono text-sm">unavailable</span>. Some game
          versions also refuse to decode unit-queue commands; when that happens the
          production numbers say so instead of reporting zero.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-2xl font-semibold">Not built yet</h2>
        <p className="max-w-3xl text-ink-muted">
          Being straight about the roadmap: peer comparison against an Elo cohort, opening
          classification beyond the four it currently recognises, and any kind of model-based
          skill estimate are all <em>planned, not implemented</em>. They need a corpus of
          analysed games first, which is what the stored-replay index is being built toward.
        </p>
      </section>
    </div>
  );
}
