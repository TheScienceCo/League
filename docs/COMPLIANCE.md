# Scope and compliance

This project is built as **post-game coaching**. That is a product decision with
architectural consequences, and this document records both.

## What it does

Retrospective analysis of match history and timeline data — the same data a
player can already see for their own completed games, obtained through the public
Riot Games API.

## What it deliberately does not do

**No live-game integration.** The `RiotProvider` interface exposes no
spectator, live-client, or in-progress endpoints at all. There is nothing to
disable, because the capability was never built. A reader can verify this by
reading `services/riot/protocol.py`: the entire surface is account lookup,
summoner lookup, ranked standings, match ids, completed matches, and completed
match timelines.

**No hidden information.** Everything surfaced about a match is information the
player either had at the time or could see afterwards in their own match history.

**No gameplay automation.** Nothing in the codebase reads game memory, sends
input, or interacts with a running client.

**No unfair live advantage.** The product's outputs are aggregate statistics and
model estimates over historical games. They are useful for review between games,
not for decisions during one.

## The risk model's feature restriction

The most interesting compliance property is in the map-risk model, and it is
enforced rather than merely intended.

Historical timelines *do* contain enemy positions. The model is nevertheless
restricted to information the player could legitimately have had at that moment:

- their own position, and distances to fixed map landmarks (the pits, their base)
- the game clock and phase
- their own team's gold state and their own level
- the objective state, derived only from what has already happened
- nearby deaths in the last minute — kills are announced to every player

It is **never** given live enemy positions. This is partly principle and partly a
useful property: a model that never needed hidden information cannot leak it, and
could not be repurposed into a live advantage even if someone tried.

`tests/test_spatial_and_roams.py::test_risk_model_never_sees_enemy_positions`
asserts this against the actual feature list, so the property survives future
edits rather than depending on someone remembering.

## Riot API policy considerations

The architecture takes these seriously rather than treating them as an
afterthought:

**Rate limiting is client-side and shared.** `services/riot/rate_limit.py`
enforces both application windows simultaneously (20/s and 100/2min on a personal
key) using a Redis-backed sliding window, so several worker processes share one
budget rather than each assuming it has the whole thing. `Retry-After` is honoured
on 429, and the penalty is applied globally so every in-flight caller backs off
together.

**Expensive operations are opt-in and explicit.** Resolving every participant's
rank costs ~10 extra API calls per match. It is off by default, on for seeding
against the simulator, and the flag is documented where it appears. `riftlab seed`
refuses to run against a live key entirely — it would be thousands of calls.

**Ingestion is idempotent and skips known matches**, so re-running a job costs
almost nothing rather than re-fetching everything.

**Errors are handled, not swallowed.** 404 is a domain answer and surfaces
immediately; 429 and 5xx retry with backoff; 401/403 says the key is expired or
unauthorised rather than retrying pointlessly.

**Personal keys expire every 24 hours.** The app degrades to the simulator when
no key is configured rather than failing, so a stale key does not brick a
running instance.

If you deploy this publicly you will need a production API key and must follow
Riot's Developer Portal policies, including their rules on branding, on
attribution, and on what may be monetised. Nothing here is endorsed by or
affiliated with Riot Games.

## Data handling

- The only personal data stored is what the Riot API returns for a public
  account: PUUID, Riot ID, summoner level, ranked standing, and match records.
- Ingestion is explicit and per-account. Nothing is crawled in the background.
- `docker compose down -v` removes everything.

## On the simulator

Without an API key the application serves a deterministic match simulator in the
Match-V5 payload shape, so the whole pipeline is runnable and testable without
credentials.

It is a **data generator, not a model of League of Legends**. Nothing learned
from simulated matches says anything about real players, and nothing in this
repository claims otherwise. It exists so the pipeline can be exercised end to
end, so tests have realistic fixtures, and so the methodology can be checked
against structure we know is there.

Simulated matches are marked `data_source = "mock"` in the database, so they can
never be silently mistaken for real ones.

## On causal claims

Every analysis here is observational. A behaviour that separates rank bands may
do so because it causes better outcomes, because better players happen to do it,
or because both share a cause the data cannot see.

This is not hedging boilerplate — it changes the wording of the product. Region
insights say "is associated with a 2.3× higher probability", never "causes".
Skill Gap reports carry their caveats through the API into the UI. Model-derived
columns are named as estimates (`expected_deaths`, `mean_position_risk`) and the
spatial endpoints refuse to return a payload without a disclaimer attached — there
is a test for that too.
