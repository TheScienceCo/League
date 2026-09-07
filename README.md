# Rift Lab

Post-game League of Legends analytics and coaching. Rift Lab ingests match
history and timeline data, derives higher-order statistics from it, and compares
a player against peers who share their role, champion, rank, patch and game
length.

The point is the *derivation*. Nothing in the product is a raw Riot API field
rendered to a page — every figure is a differential against the lane opponent, a
rate, a share, a cohort percentile, or a model output.

```
Riot ID ─→ match ids ─→ match + timeline ─→ normalized Postgres
                                                   │
                                     ┌─────────────┴─────────────┐
                              per-match features          corpus-wide analytics
                          (differentials, shares,     (peer cohorts, map risk
                           rates, conditional splits)   surface, rank-separation
                                     │                    model, roam baselines)
                                     └─────────────┬─────────────┘
                                              coaching output
```

---

## Quick start

You do **not** need a Riot API key. Without one the application serves a
deterministic match simulator in exactly the Match-V5 payload shape, and the
entire pipeline — ingestion, feature engineering, cohorts, models — runs
identically against it.

```bash
git clone <this repo> && cd League
cp .env.example .env
make demo
```

`make demo` starts Postgres, Redis, the API, a worker and the web app; seeds a
corpus of ~640 matches spanning every rank band; and trains the models. It takes
a few minutes. Then:

- **Web app** — <http://localhost:3000>, search for `RiftLabDemo#NA1`
- **API docs** — <http://localhost:8000/docs>

Other demo accounts: `ChallengerSmurf#KR1`, `GoldPlateau#EUW`, `IronWill#NA1`.
Any other Riot ID also resolves, to a deterministic synthetic player.

### With a real Riot API key

```bash
# in .env
RIOT_API_KEY=RGAPI-...
RIOT_USE_MOCK=false
```

Then ingest accounts you have permission to analyse:

```bash
docker compose exec worker riftlab ingest 'Name#TAG' --count 30
docker compose exec worker riftlab refresh-analytics
```

Note that `riftlab seed` refuses to run against a live key — it would be several
thousand API calls. Cohort quality depends on corpus size and rank spread, so a
freshly keyed instance will fall back to broad cohorts until you have ingested a
few hundred games; the UI marks every comparison that fell back.

### Without Docker

```bash
make install            # backend venv + frontend deps
createdb riftlab
cd backend && DATABASE_URL=postgresql+psycopg://...  alembic upgrade head
make api                # terminal 1
make web                # terminal 2
```

---

## What it computes

### Derived per-game metrics

Laning differentials are measured against the **lane opponent**, not the lobby
average, because that is who the laning phase is actually contested against.

| Family | Metrics |
| --- | --- |
| Laning | gold/XP/CS differential at 10 and 15, CS per minute, first-15 CS rate, lane trajectory (10–20 min slope) |
| Combat | kill participation, early deaths, deaths per 10 min, solo-kill differential, damage per gold, damage share, gold share |
| Efficiency | **Resource Conversion Efficiency** (raw and champion-normalised) |
| Vision | vision score, wards placed, wards cleared, control wards — all per minute |
| Objectives | participation (credited *or* present), dragon and Baron/Herald splits, setup timing score, deaths before objectives |
| Game state | share of game spent ahead, damage and CS per minute while ahead vs behind, lead-to-win conversion, comeback rate |
| Roaming | roam count, value per roam, CS sacrificed, success rate |
| Positioning | mean positional death risk, expected deaths, deaths above expectation, high-risk exposure share |

### Resource Conversion Efficiency

```
RCE = champion damage share ÷ team gold share
```

A player who takes 30% of their team's gold and produces 30% of its damage
scores 1.0, regardless of game length or how fed the team was — both sides of
the ratio are shares. It does *not* control for champion, because a marksman
converts gold into damage far better than an enchanter and that is a property of
the pick. The normalised form is a z-score against the narrowest available
champion × role × rank × patch cohort, which removes exactly that.

### Map risk

Every timeline frame is an *exposure*: a player, at a position, at a time,
labelled with whether they died within the next 30 seconds. Aggregating over a
32×32 grid gives an empirical risk surface; a gradient-boosted classifier over
the same exposures with richer features gives the per-player figures.

The output reads like:

> Being in blue bot jungle during mid game is associated with a 2.3× higher
> probability of dying within 30s, compared with the average position for this
> role and phase (n=61 observations).

The model is deliberately restricted to information the player could
legitimately have had at that moment — their own position, their own team's
economy, the clock, the objective state, and events announced to everyone. It is
never given live enemy positions, even though the historical timeline contains
them. There is a test asserting this.

### Skill Gap Analysis

The headline ML feature, and the one where the methodology matters most.

Nobody writes down that CS/min matters more than vision score. A model is
trained to predict a player's **rank band** from residualized behavioural
features, and the features it leans on are the answer.

1. **Residualize.** Every feature is centred on its champion × role × patch ×
   duration control group, with group means shrunk toward broader means in
   proportion to how little data the group has. Without this the model happily
   "discovers" that Master players have more damage share — when in fact they
   picked more marksmen.
2. **Fit.** A gradient-boosted classifier, cross-validated with `GroupKFold` on
   PUUID so no player appears in both folds. Without that grouping the model
   memorises players rather than behaviours and every score is inflated.
3. **Attribute.** Permutation importance on a held-out, player-disjoint split,
   reported alongside each feature's univariate rank correlation — a feature can
   rank highly for either reason and the difference matters.
4. **Compare.** Each behaviour's gap to the target band is expressed in pooled
   standard deviations, signed so positive always means "the target band does
   this better". Ranking by `importance × gap` surfaces a behaviour only when it
   both separates ranks *and* is one this player is behind on.

On the seeded corpus the model reaches a cross-validated rank-ordering Spearman
of **0.91** and balanced accuracy of **0.62** against a 0.20 chance level,
predicting rank band from a *single game* (median 1 game per player). The
headline metric is rank ordering rather than accuracy because the target is
ordinal: being one band out is a different kind of error from being four out,
and argmax accuracy cannot express that.

Sample output:

> The five behaviours separating you most from Diamond:
> 1. Damage per minute — gap 0.75σ, model weight 40%
> 2. Damage per gold — gap 0.52σ, model weight 25%
> 3. Vision score per minute — gap 0.69σ, model weight 7%
> 4. CS per minute (first 15) — gap 0.74σ, model weight 5%
> 5. Wards cleared per minute — gap 0.83σ, model weight 3%

### Decision Value Added (experimental)

DVA compares the win-probability change that actually followed a moment against
what usually follows historically similar moments, found by nearest neighbours
over state vectors drawn from *other* matches. The attribution step is the weak
link and is deliberately conservative: win probability is a property of ten
players, so a player is credited with only the share of the residual their own
involvement supports. It is labelled experimental throughout, excluded from the
Skill Gap feature set, and its numbers should be read directionally.

---

## Pages

| Page | What it shows |
| --- | --- |
| `/` | Search, demo accounts, capability summary |
| `/player/[platform]/[riotId]` | Dashboard: headline metrics vs cohort, consistency, lead conversion, rolling form, roles, champions |
| `.../matches` | Match history with per-game derived metrics |
| `/match/[matchId]` | Single-match analysis: economy timeline vs lane opponent, deaths in context with modelled risk, objective setup, roams, coaching observations |
| `.../advanced` | Every derived metric against its peer cohort, grouped by family |
| `.../map` | Where the player stands and dies, plus risk-adjusted positioning |
| `.../skill-gap` | Behaviours separating them from the next band, with model quality |
| `.../compare` | Side-by-side against a chosen rank band |
| `/insights` | Which behaviours separate ranks overall |
| `/map` | Global death-risk heatmap by role, phase and rank |
| `/methodology` | How every number is produced, and what it does not support |

---

## Development

```bash
make test        # fast suite (~30s, SQLite, no containers)
make test-all    # adds the end-to-end ML suite (~1 min)
make lint        # ruff + mypy + tsc
make format      # auto-fix
```

The test suite runs against SQLite by default so it needs no containers; set
`TEST_DATABASE_URL` to exercise the Postgres dialect. The models use
`with_variant` column types so both work, and no query depends on a
Postgres-only operator.

The end-to-end ML suite is marked `slow` and excluded from the default run. It
ingests a rank-spanning corpus, trains a real model, and asserts that the
pipeline **recovers structure the simulator planted** — that the behaviours the
simulator ties to latent skill are the ones the model ranks highly. That is a
check on the methodology, not on League of Legends.

### Layout

```
backend/     FastAPI, ingestion, analytics, ML  (see backend/README.md)
frontend/    Next.js App Router + TypeScript
infra/       Postgres init scripts
docs/        architecture, feature definitions, compliance notes
```

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — components, data model, request and job flows
- [Feature engineering](docs/FEATURES.md) — the definition and rationale of every derived metric
- [Compliance](docs/COMPLIANCE.md) — scope, Riot API policy, and what this deliberately does not do

---

## Scope and honesty

All analysis is **retrospective**, over match history a player can already see
for their own games. There is no live-game or spectator integration, no
automation of gameplay, and nothing surfaced that a player could not have known
at the time.

Everything here is observational. A behaviour that separates ranks may do so
because it causes better outcomes, because better players happen to do it, or
because both share a cause this data cannot see. No claim of causation is made
anywhere, and the phrasing throughout — "associated with", never "because" —
reflects that. Model-derived figures are labelled as estimates and carry their
own caveats through the API into the UI.

Simulated matches are a data generator, not a model of League of Legends.
Nothing learned from them says anything about real players; they exist so the
pipeline can be exercised end to end and so tests have realistic fixtures.

Not endorsed by or affiliated with Riot Games.
