export const metadata = {
  title: "Methodology",
  description:
    "How a replay is parsed, what each metric means, and which questions a replay file cannot answer.",
};

const METRICS = [
  {
    label: "Feudal / Castle / Imperial Age reached",
    tag: "observed",
    body: "Taken from the game's own age transitions as recorded in the replay, not from a research command we have to decode. This is the most reliable figure the file contains. The 'vs opponent' row is the gap to the fastest other player; negative is faster.",
  },
  {
    label: "Average / peak banked resources",
    tag: "inferred",
    body: "Definitive Edition replays carry periodic sync packets with a per-player resource total. The packet layout is community reverse-engineered rather than documented, and the value combines food, wood, gold and stone — there is no per-type split. Directionally right; not exact.",
  },
  {
    label: "Time above 1000 banked",
    tag: "inferred",
    body: "How long you sat on more than roughly a Town Center's worth of unspent resources. Same sync-packet caveat. 1000 is a threshold we chose, not a rule of the game.",
  },
  {
    label: "Longest gap between villager queues",
    tag: "reconstructed",
    body: "The longest stretch between two villager queue commands. It is a proxy for Town Center idle time, and an imperfect one: a player who queues five villagers at once leaves a long gap while the Town Center is busy the whole time. Treat a large number as a prompt to go look, not as proof.",
  },
  {
    label: "Buildings placed / technologies researched",
    tag: "observed",
    body: "Counts of build and research commands. A placed foundation can be cancelled or destroyed before it finishes, so this counts intent rather than completed structures.",
  },
  {
    label: "Effective APM",
    tag: "observed",
    body: "Computed by the mgz parser, which excludes duplicated and spam orders. It measures activity, not skill — a high figure is not automatically better.",
  },
  {
    label: "Opening",
    tag: "reconstructed",
    body: "The first military production building placed before Castle Age names the opening: Archery Range, Stable, Barracks or Watch Tower. None before Castle reads as a fast castle. It recognises those four cases and reports 'unclassified' otherwise rather than guessing.",
  },
];

const TAGS: Record<string, { style: string; meaning: string }> = {
  observed: {
    style: "bg-emerald-500/15 text-emerald-500",
    meaning: "Read directly out of the command stream. Exact.",
  },
  reconstructed: {
    style: "bg-sky-500/15 text-sky-500",
    meaning: "Derived from observed commands under a stated assumption.",
  },
  inferred: {
    style: "bg-amber-500/15 text-amber-500",
    meaning:
      "From sync packets whose field meanings are reverse-engineered. Directionally right, not exact.",
  },
  unavailable: {
    style: "bg-surface-border text-ink-muted",
    meaning: "Not recoverable from a replay. Reported as null, never as zero.",
  },
};

export default function MethodologyPage() {
  return (
    <div className="max-w-3xl space-y-12 py-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Methodology</h1>
        <p className="text-ink-muted">
          What is measured, how, and where the limits are.
        </p>
      </header>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">A replay is a command stream</h2>
        <p className="text-ink-muted">
          An <code className="font-mono text-sm">.aoe2record</code> file stores the inputs
          players sent to the game engine — move here, build there, research this — together
          with the tick each was sent on. Replaying those inputs against the same engine
          reproduces the game, which is how the in-game viewer works.
        </p>
        <p className="text-ink-muted">
          The consequence for analysis is the thing worth understanding: the file records{" "}
          <strong>what players did</strong>, not <strong>what happened</strong>. &ldquo;Queued
          a villager at 4:32&rdquo; is in there. &ldquo;A villager was created&rdquo; is not,
          because the queue may be cancelled or the Town Center destroyed. Unit deaths, kills
          and combat outcomes are absent entirely.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Every number is labelled</h2>
        <p className="text-ink-muted">
          Because the file answers some questions exactly, some approximately and some not at
          all, each metric carries how it was obtained:
        </p>
        <dl className="space-y-3">
          {Object.entries(TAGS).map(([tag, { style, meaning }]) => (
            <div key={tag} className="flex gap-3">
              <dt>
                <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${style}`}>
                  {tag}
                </span>
              </dt>
              <dd className="text-sm text-ink-muted">{meaning}</dd>
            </div>
          ))}
        </dl>
        <p className="text-sm text-ink-muted">
          An unavailable metric renders as the word &ldquo;unavailable&rdquo;, never as a
          zero or a dash that could be mistaken for a measurement of nothing.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">The metrics</h2>
        <div className="space-y-5">
          {METRICS.map((m) => {
            const tag = TAGS[m.tag]!;
            return (
            <div key={m.label} className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-semibold">{m.label}</h3>
                <span
                  className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${tag.style}`}
                >
                  {m.tag}
                </span>
              </div>
              <p className="text-sm text-ink-muted">{m.body}</p>
            </div>
            );
          })}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">When parsing degrades</h2>
        <p className="text-ink-muted">
          Action encodings change between game versions, and the parser does not decode every
          one. Two failure modes are handled explicitly rather than hidden:
        </p>
        <ul className="list-inside list-disc space-y-2 text-ink-muted">
          <li>
            <strong>Unit-queue commands do not decode.</strong> On some versions these arrive
            as unparseable actions. Production metrics then report unavailable, and the
            analysis carries a warning — rather than reporting that you queued no villagers.
          </li>
          <li>
            <strong>A large share of actions do not decode.</strong> Above a quarter, the
            build-order detail is flagged as incomplete.
          </li>
          <li>
            <strong>The file will not parse at all.</strong> Older versions are rejected with
            an explanation instead of a generic error.
          </li>
        </ul>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Determinism</h2>
        <p className="text-ink-muted">
          The same file always produces the same analysis: nothing samples, randomises or
          reads a clock. Re-uploading a file you have already analysed returns the stored
          result, keyed by the SHA-256 of its bytes.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">What is not here yet</h2>
        <p className="text-ink-muted">
          Peer comparison against an Elo cohort, scouting and map-control metrics, engagement
          detection and any model-based skill estimate are <em>not implemented</em>. Several
          of them are bounded by the command-stream limits above rather than by effort:
          engagement analysis in particular would require outcome data the file does not
          contain, so it would have to be inferred from unit movement and stated as such.
        </p>
      </section>
    </div>
  );
}
