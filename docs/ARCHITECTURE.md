# Architecture

## Components

| Service | Responsibility |
| --- | --- |
| `web` | Next.js App Router. Server components fetch the API directly; client components go through a rewrite so the browser never learns the backend's address. |
| `api` | FastAPI. HTTP layer only — routers validate, call a service, and serialise. |
| `worker` | The same image as `api`, idling. Long jobs (ingestion, corpus refreshes, training) are `exec`'d into it so they never share a process with request handling. |
| `postgres` | System of record. Normalized Riot payloads plus every derived table. |
| `redis` | Optional. Shared Riot rate-limit budget across processes, and response caching. Every caller degrades gracefully without it. |

## Why the backend is synchronous

Every request path either does bulk SQL or runs pandas/scikit-learn code that is
itself blocking. FastAPI executes `def` endpoints in a threadpool, which gives
the concurrency we need without colouring the entire analytics stack `async`.

The Riot HTTP client *is* async, and runs inside the ingestion pipeline, which is
where concurrency actually matters: several match fetches in flight under a
shared rate-limit budget.

## The provider seam

Everything downstream depends on `services.riot.RiotProvider`, a Protocol —
never on the concrete HTTP client. That buys three things:

1. The ingestion pipeline is unit-testable without network access.
2. The app is fully runnable without an API key, via `MockRiotProvider`.
3. Any endpoint whose exact shape is uncertain can be stubbed behind the same
   interface rather than guessed at.

The interface deliberately exposes no live-game, spectator, or in-progress
endpoints at all. That is a design constraint, not an oversight.

## Data model

```
summoners ──< league_entries
    │
matches ──< match_teams
    ├──< match_participants          faithful Match-V5 copies
    ├──< timeline_frames             one row per (participant, minute)
    ├──< timeline_events             kills, wards, objectives, buildings
    ├──< participant_features        ← the boundary: everything here is derived
    ├──< roam_events
    └──< objective_setups

cohort_stats      peer baselines, materialised at several specificities
map_risk_cells    empirical death-risk surface over a 32x32 grid
ml_models         registry: metrics, importances, artifact paths
ingest_jobs       job tracking for the async ingestion API
```

`participant_features` is the boundary between ingestion and analytics. Nothing
in it is a raw Riot field. Columns are explicit rather than a JSON blob because
the table *is* the ML feature matrix, and we want the database — not a
convention — enforcing its schema.

### Portable column types

Production is Postgres; the test-suite runs on SQLite so `pytest` needs no
containers. `db/types.py` defines variant types (`JSONVariant`, `IntArray`,
`BigIntPK`) that use the rich Postgres type where available and fall back
otherwise. `BigIntPK` exists because SQLite only auto-assigns rowids for a column
declared exactly `INTEGER PRIMARY KEY`; a `BIGINT` one fails on NOT NULL. No
query in the codebase relies on a Postgres-only operator, so both behave
identically — `_at_least_one()` in `analytics/player.py` is the pattern for
constructs like `greatest()` that only one dialect spells that way.

## Ingestion flow

```
resolve Riot ID ─→ account + summoner + league entries persisted
       │
       ├─→ page match ids (queue-filtered)
       ├─→ skip ids already stored (unless force_refresh)
       └─→ for each match, under a concurrency semaphore:
              fetch match ──┐
              fetch timeline┘ (async, rate-limited)
                    │
              persist match, teams, participants   ┐
              persist timeline frames + events      │ short sync transactions
              backfill participant ranks            │
              compute features, objectives, roams  ┘
```

No transaction is ever held open across a network call: the async fetches happen
outside the session scope, and the database work happens in short synchronous
transactions between awaits.

### Injectable session scope

`IngestionService` takes its session scope as a constructor argument. The worker
uses the default (each unit of work opens its own short transaction). The API
passes a scope bound to the current request for *identity resolution*, so the
resolved account is visible to the rest of the request — but deliberately not for
match ingestion, because the request session is closed the moment the response is
sent. Tests inject a scope over the test session, which is why they exercise the
real pipeline rather than a mock of it.

### Idempotency

Re-running a job for the same player is cheap and safe. Matches already stored
are skipped, every writer is an upsert, and re-ingesting a match replaces its
timeline rather than duplicating it. There are tests for both.

## Corpus-wide refresh

Per-match features are computed at ingest time. Anything that needs a
*population* is rebuilt by `analytics/refresh.py`, and the ordering is
load-bearing:

1. **Cohorts** — peer baselines at every specificity level.
2. **RCE normalisation** — reads those cohorts.
3. **Risk grid** and **risk model** — fit over timeline exposures.
4. **Per-match risk scoring** — populates the positioning feature columns.
5. **Cohorts, second pass** — the risk columns did not exist during step 1, so
   without this they have no baselines and every comparison against them comes
   back empty. There is a regression test.
6. **Roam expected values** — each roam against its own (role, destination) peer
   group.
7. **Skill Gap model** — whose feature set includes the risk columns.

## Cohort resolution

A cohort is a conjunction of control variables: role, champion, rank band, patch,
duration bucket. Fully specifying all five gives the cleanest comparison and the
emptiest cohorts, so the system materialises a *chain* of progressively broader
cohorts and, at query time, walks it from narrowest to broadest and uses the
first with enough observations.

`CohortService.resolve_detail()` returns the cohort **and** whether the search had
to widen, and that flag is carried all the way into the UI. A caller always knows
what a player was actually compared against.

## ML layer

Estimators are constructed through `ml/registry.make_classifier`, which prefers
XGBoost when the `boost` extra is installed and falls back to scikit-learn
otherwise. Call sites never import either directly, which is what keeps "add
XGBoost later" a dependency change rather than a refactor. Class balancing is
applied via `sample_weight` at fit time rather than a backend-specific
`class_weight` parameter, because the two backends disagree on the latter and
both accept the former.

Fitted artifacts are written with joblib and described in `ml_models`, so the API
can report a model's metrics, training size and feature importances without
loading the estimator.

## Frontend

Server components own data fetching and render on request; client components are
limited to genuinely interactive pieces (search, the ingest button with its job
polling, charts). Two consequences worth knowing:

- Props crossing into a client component must be serialisable. `HorizontalBars`
  takes a `format: "decimal" | "percent" | "sigma"` string rather than a
  formatter callback for exactly this reason.
- Chart entry animation is disabled everywhere: on a dashboard this dense it
  delays first paint for no benefit and makes visual checks unreliable.

The map is drawn as inline SVG rather than an image: the lanes, river and pits
are the only landmarks the analysis refers to, it stays sharp at any size, and it
carries no third-party art. World coordinates run 0–15000 with y increasing
upward, so the scene is flipped once on the y axis rather than converting every
point.

## Testing strategy

| Suite | What it pins |
| --- | --- |
| `test_geometry`, `test_constants` | Pure functions with hand-checkable answers |
| `test_features` | Feature arithmetic, on hand-built matches with known results |
| `test_cohorts` | Fallback behaviour, and that per-game comparison is used |
| `test_ml` | That residualization removes the confound it claims to and preserves signal |
| `test_ingest` | The real pipeline end to end, including idempotency |
| `test_spatial_and_roams` | Exposure labelling, risk surface sanity, roam valuation |
| `test_api` | HTTP contracts, error shapes, that disclaimers are present |
| `test_skill_gap_e2e` *(slow)* | That the model recovers structure the simulator planted |

The last one is the methodology's self-check. It is marked `slow` and excluded
from the default run.
