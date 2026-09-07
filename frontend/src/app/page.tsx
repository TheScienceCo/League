import Link from "next/link";

import { SearchForm } from "@/components/search-form";
import { Card, Disclaimer } from "@/components/ui";
import { api } from "@/lib/api";
import { tierLabel } from "@/lib/format";
import type { PlayerSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

const DEMO_ACCOUNTS = [
  { riotId: "RiftLabDemo#NA1", platform: "na1", note: "Platinum mid-table" },
  { riotId: "ChallengerSmurf#KR1", platform: "na1", note: "Master+" },
  { riotId: "GoldPlateau#EUW", platform: "na1", note: "Gold" },
  { riotId: "IronWill#NA1", platform: "na1", note: "Iron" },
];

const CAPABILITIES = [
  {
    title: "Derived, not displayed",
    body: "Gold and XP differentials against the lane opponent, damage per gold, damage share versus gold share, objective participation, vision rates — computed from match and timeline data rather than read off a scoreboard.",
  },
  {
    title: "Resource Conversion Efficiency",
    body: "Output share divided by resource share, then normalised against champion, role, rank, patch and game length. A player who takes 30% of the gold and produces 30% of the damage scores 1.0, whatever they play.",
  },
  {
    title: "Map risk modelling",
    body: "Every timeline frame is an exposure labelled with whether a death followed within 30 seconds. The result is a risk surface by region and game phase, and a per-player figure for deaths beyond what positioning implied.",
  },
  {
    title: "Skill gap analysis",
    body: "Nothing is hard-coded about what makes a player good. A model is trained to separate rank bands from residualized behaviour, and the behaviours it leans on are the answer.",
  },
];

export default async function LandingPage() {
  let players: PlayerSummary[] = [];
  let apiReachable = true;
  try {
    players = await api.listPlayers(12);
  } catch {
    apiReachable = false;
  }

  return (
    <div className="space-y-8">
      <section className="pt-6">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Post-game analytics that go past KDA
        </h1>
        <p className="mt-3 max-w-2xl text-ink-muted">
          Rift Lab ingests match history and timeline data, derives higher-order
          statistics from it, and compares a player against peers who share their
          role, champion, rank, patch and game length.
        </p>
        <div className="mt-5 max-w-xl">
          <SearchForm autoFocus />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <span>Try:</span>
          {DEMO_ACCOUNTS.map((account) => (
            <Link
              key={account.riotId}
              href={`/player/${account.platform}/${encodeURIComponent(account.riotId)}`}
              className="rounded border border-surface-border bg-surface-raised px-2 py-1 hover:border-accent"
            >
              {account.riotId}
              <span className="ml-1.5 text-ink-faint">{account.note}</span>
            </Link>
          ))}
        </div>
        {!apiReachable && (
          <Disclaimer>
            The API is not reachable. Start it with{" "}
            <code className="font-mono">docker compose up</code> or{" "}
            <code className="font-mono">make dev</code>.
          </Disclaimer>
        )}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        {CAPABILITIES.map((item) => (
          <Card key={item.title} title={item.title}>
            <p className="text-sm leading-relaxed text-ink-muted">{item.body}</p>
          </Card>
        ))}
      </section>

      {players.length > 0 && (
        <Card
          title="Players already analysed"
          subtitle="Accounts with ingested matches in this instance"
        >
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {players.map((player) => {
              const rank = player.ranks[0];
              const riotId =
                player.game_name && player.tag_line
                  ? `${player.game_name}#${player.tag_line}`
                  : player.puuid;
              return (
                <li key={player.puuid}>
                  <Link
                    href={`/player/${player.platform}/${encodeURIComponent(riotId)}`}
                    className="flex items-center justify-between rounded border border-surface-border px-3 py-2 text-sm hover:border-accent"
                  >
                    <span className="truncate">{riotId}</span>
                    <span className="ml-2 shrink-0 text-xs text-ink-faint">
                      {rank ? tierLabel(rank.tier_group) : "—"}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      <Card title="Scope and compliance">
        <ul className="space-y-1.5 text-sm text-ink-muted">
          <li>
            Analysis is retrospective, over match history a player can already see
            for their own games. There is no live-game or spectator integration.
          </li>
          <li>
            No hidden enemy information is exposed, and the risk model is
            deliberately trained without live enemy positions among its inputs.
          </li>
          <li>
            Model outputs are labelled as estimates and describe association
            within a historical dataset, not causation.
          </li>
        </ul>
      </Card>
    </div>
  );
}
