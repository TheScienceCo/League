# AoE2 Analytics Platform - Architecture

## System Overview

This platform reconstructs complete game state from Age of Empires II replay files and derives comprehensive analytics to quantify player skill and provide actionable coaching insights.

## Components

| Service | Responsibility |
| --- | --- |
| `web` | Next.js 15 frontend. Server/client components. Search, upload, dashboards, timeline visualization. |
| `api` | FastAPI. HTTP layer — routers validate, call services, serialize responses. |
| `worker` | Background job processor. Replay parsing, state reconstruction, metrics calculation happen here asynchronously. |
| `postgres` | System of record. Normalized replay data, game states, events, metrics, coaching insights. |
| `redis` | Job queue (Celery-like) and response caching. Used for async replay processing. |

## Data Pipeline

```
Upload Replay File (.aoe2record)
         ↓
    Parser Service
    (aoc-mgz or mock)
         ↓
    Event Stream
   (normalized)
         ↓
State Reconstruction
 (snapshots @ 10s)
         ↓
Metrics Calculator
  (economy, military,
   scouting, strategic)
         ↓
Coaching Report
   Generator
         ↓
  Store in DB
    + Cache
         ↓
  Display in UI
```

## Service Layer Architecture

### app.services.aoe
- **parser.py**: Replay file parsing abstraction
  - Adapter over aoc-mgz library
  - Deterministic mock for MVP testing
  - Handles .aoe2record format parsing

### app.services.replay
- **ingest.py**: Complete processing pipeline orchestration
  - File validation and storage
  - Coordinates parser → reconstructor → metrics → reporting
  - Error handling and retry logic
- **state_reconstruction.py**: Event → state conversion
  - Maintains cumulative game state
  - Generates snapshots at configurable intervals
  - Tracks resources, population, units, buildings, technologies

### app.services.analytics
- **metrics.py**: Derives all game metrics from state/events
  - Economy: TC idle time, resource float, collection rates
  - Military: units killed/lost, engagement efficiency
  - Scouting: coverage, discovery timing
  - Strategic: reaction latency, tempo score
  - All metrics normalized by Elo cohort and map type

### app.services.coaching
- **report.py**: Generates human-readable insights
  - Identifies strengths and weaknesses
  - Quantifies impact of decisions
  - Recommends improvements with time estimates

### app.services.feature_engineering
- Peer comparison baseline calculation
- Cohort aggregation and percentile ranking
- Statistical analysis

### app.services.ml (Future)
- Skill gap identification models
- Win probability estimation
- Player archetyping

## Data Model

### Core Tables

```
players
  ├─ id (PK)
  ├─ username (unique)
  ├─ steam_id (unique, optional)
  └─ stats (wins, losses, mean_elo)

matches
  ├─ id (PK)
  ├─ replay_file_id (FK)
  ├─ map_type (enum)
  ├─ duration_seconds
  └─ player_count

match_players (junction)
  ├─ match_id (PK, FK)
  ├─ player_id (PK, FK)
  ├─ civilization
  ├─ team
  ├─ result (win/loss/draw)
  └─ elo_before, elo_after

replay_files
  ├─ id (PK)
  ├─ match_id (FK)
  ├─ file_hash (unique)
  ├─ storage_path
  └─ status (uploaded → parsing → parsed → analyzed → completed)

events
  ├─ id (PK)
  ├─ match_id (FK)
  ├─ player_id (FK)
  ├─ timestamp_ms
  ├─ event_type (enum)
  └─ data (JSON)

game_states
  ├─ id (PK)
  ├─ match_id (FK)
  ├─ player_id (FK)
  ├─ timestamp_ms
  └─ snapshot (JSON: age, resources, units, buildings, etc.)

engagements
  ├─ id (PK)
  ├─ match_id (FK)
  ├─ start/end timestamps
  ├─ participants
  └─ outcome metrics (value killed/lost)

match_metrics
  ├─ id (PK)
  ├─ match_id (FK, unique)
  ├─ player_id (FK)
  ├─ tc_idle_time_ms
  ├─ resource_float_peak/average
  ├─ age_up_timing_ms
  ├─ military_value_killed/lost
  ├─ engagement_efficiency
  ├─ scouting_coverage_percent
  └─ [30+ derived metrics]

player_metric_percentiles
  ├─ player_id (FK)
  ├─ metric_name
  ├─ elo_band_min/max
  ├─ percentile_rank (0-100)
  └─ cohort_size

coaching_insights
  ├─ match_id (FK)
  ├─ player_id (FK)
  ├─ category (economy, military, build, etc.)
  ├─ title & description
  ├─ magnitude
  ├─ recommendation
  └─ estimated_impact
```

### Key Design Decisions

**JSON Columns**
- Events and game states stored as JSON for flexibility
- Avoids premature schema rigidity
- Allows parser improvements without migrations

**Feature Versioning**
- All metrics tagged with version
- Enables reproducible historical analysis
- Supports model iteration

**Denormalized Stats**
- Player wins/losses cached at player level
- Materialized cohort percentiles (periodic refresh)
- Trades space for query speed on dashboards

## API Routes

```
POST   /api/v1/aoe2/replays/upload
GET    /api/v1/aoe2/replays/{id}/status
GET    /api/v1/aoe2/replays/{id}/download

GET    /api/v1/aoe2/matches/{id}
GET    /api/v1/aoe2/matches/{id}/detail
GET    /api/v1/aoe2/matches/{id}/metrics/{player_id}
GET    /api/v1/aoe2/matches/{id}/timeline/{player_id}
GET    /api/v1/aoe2/matches/{id}/events/{player_id}

GET    /api/v1/players/{id}
GET    /api/v1/players/{id}/matches
GET    /api/v1/players/{id}/metrics

GET    /api/v1/analytics/percentiles
GET    /api/v1/analytics/skill-gap/{player_id}

GET    /health
```

## Processing Pipeline

### Stage 1: Upload & Validation
- File size check (max 100MB)
- Format validation (.aoe2record)
- Hash calculation for deduplication
- Storage to `/data/replays/{hash}/`

### Stage 2: Parsing
- Extract action IDs, timestamps, player IDs from binary
- Parse game events (build, unit creation, death, etc.)
- Extract metadata (map, duration, players, civs)
- Output: Normalized event list + metadata

### Stage 3: State Reconstruction
- Process events chronologically
- Maintain cumulative state per player
- Generate snapshots every N seconds (default 10s)
- Calculate derived values (army value, economy value)

### Stage 4: Metrics Calculation
- Analyze state snapshots and events
- Compute 30+ metrics per player
- Compare against peer cohorts
- Generate percentile ranks

### Stage 5: Coaching Report
- Identify strengths (top 3)
- Identify mistakes (top 3)
- Recommend improvements (top 3)
- Estimate Elo-equivalent performance

### Stage 6: Storage
- Insert into database (atomic transaction)
- Cache percentiles in Redis
- Mark replay processing complete

## Testing Strategy

### Unit Tests
- Parser: mock generates valid replay structure
- State Reconstruction: events → correct state changes
- Metrics: specific calculations (TC idle time, etc.)
- Coaching: report generation and formatting

### Integration Tests
- End-to-end replay processing pipeline
- Database round-trip
- API endpoint responses

### Test Data
- Mock replay with known metrics (deterministic)
- Sample replays in `data/samples/`
- Synthetic player histories for cohort testing

## Frontend Architecture

### Pages

| Route | Purpose |
| --- | --- |
| `/` | Landing page, player search, recent games |
| `/players/:id` | Player dashboard, stats, trends |
| `/players/:id/matches` | Recent match list with quick stats |
| `/matches/:id` | Full match analysis with timeline |
| `/skill-gap/:id` | Radar chart showing skill dimensions |
| `/upload` | Replay upload form with drag-and-drop |

### Key Components
- `TimelineChart` — Game progress visualization
- `EconomyGraph` — Resource collection/spending over time
- `SkillRadar` — Skill gap percentiles
- `MetricsTable` — Detailed metric display
- `EventList` — Chronological event stream

## Deployment & Scalability

### Docker Compose (Development)
```
postgres:15
redis:7
api:8000 (FastAPI)
worker:background
web:3000 (Next.js)
```

### Production Considerations
- Database: PostgreSQL 15+, connection pooling
- Cache: Redis for response caching and job queue
- Async: Background worker for heavy jobs
- CDN: Static frontend assets
- Monitoring: Application logs, database metrics

### Performance
- Event indexing by match_id, timestamp
- Metric queries join match_metrics + player_metric_percentiles
- Caching: Recent player stats (1hr TTL), cohort percentiles (24hr)
- Batch inserts for events and game states

## Reproducibility & Determinism

- **No randomness** in core calculations
- Same replay file → identical metrics every time
- Feature versioning enables metric recomputation
- ML components clearly marked as estimates
- Confidence intervals on model predictions

## Error Handling

- Graceful degradation: missing replay parser → mock used
- Partial analysis: if state reconstruction fails, store raw events
- Retry logic: transient parsing errors retry automatically
- User feedback: clear error messages for invalid uploads

## Security & Privacy

- File hash verification (SHA256)
- Max file size enforcement
- No storage of credentials or API keys
- Replay file hash-based organization (prevents path traversal)
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
