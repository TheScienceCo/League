# AoE2 Analytics Platform

**Production-quality full-stack analytics and coaching platform for Age of Empires II: Definitive Edition.**

Quantify RTS skill from replay and match data by modeling economy, build execution, military efficiency, strategic decisions, timing, and decision quality. This system goes far beyond Elo, win rate, civ choice, and basic match history.

[![CI](https://github.com/TheScienceCo/League/actions/workflows/ci.yml/badge.svg)](https://github.com/TheScienceCo/League/actions/workflows/ci.yml)

---

## What This Platform Does

### Data Ingestion
- Upload `.aoe2record` replay files
- Auto-discover public multiplayer matches (optional future)
- Parse event streams and reconstruct complete game state

### Analysis Pipeline
```
player/replay
  ↓
match metadata
  ↓
replay parser (aoc-mgz)
  ↓
event stream (normalized)
  ↓
state reconstruction (snapshots @ 5-15s intervals)
  ↓
feature engineering
  ↓
player/decision metrics
  ↓
peer comparison
  ↓
ML models
  ↓
coaching insights
  ↓
interactive frontend
```

### Core Analytics Modules

1. **Economic Efficiency** — TC idle time, villager production, resource float, collection curves, spending efficiency
2. **Build Order Execution** — Opening detection, feudal/castle/imperial timings, comparison to high-Elo medians
3. **Military Efficiency** — Resources killed/lost, engagement efficiency, unit-counter effectiveness
4. **Strategic Timing** — Expansions, tech switches, reactions, defensive decisions
5. **Scouting & Information** — Coverage, discovery timing, information advantage
6. **Resource Conversion** — Efficiency of collected resources → military pressure
7. **Tempo** — Speed of converting advantages into additional advantages
8. **Skill Gap Analysis** — ML-identified behaviors separating Elo tiers
9. **Decision Value Added** — Estimated future value vs. historical comparable states
10. **Player Archetyping** — Behavior-based player clustering

### Features

| | |
| --- | --- |
| **Metrics** | 30+ derived metrics from game state and events; not raw fields |
| **Peer Comparison** | Median timings, percentile ranks; conditioned on civ, map, opening, Elo cohort |
| **Coaching Report** | Post-game insights: strengths, mistakes, most expensive decision, actionable improvements |
| **Skill Gap** | Which behaviors separate you from higher Elo; estimated Elo-equivalent per category |
| **Engagement Analysis** | Detect fights, estimate value traded, strategic outcome |
| **Interactive Timeline** | Age-ups, economy, population, military, engagements, technologies, production |
| **Deterministic** | Same replay → same metrics; no randomness; ML components clearly marked as estimates |

---

## Quick Start

```bash
git clone https://github.com/TheScienceCo/League.git
cd League
cp .env.example .env
docker compose up --build
```

- **Web UI** — <http://localhost:3000>
- **API docs** — <http://localhost:8000/docs>

The application starts with seed data and deterministic analysis (no replay parser needed initially).

### Without Docker

```bash
make venv                     # backend virtualenv
make install                  # install dependencies
make migrate                  # run database migrations
make test                     # ~200 tests, ~10s

# Then, in separate terminals:
make api                      # FastAPI server
make worker                   # background job processor
make web                      # Next.js frontend
```

---

## Architecture

### Tech Stack

| Component | Technology |
| --- | --- |
| **Frontend** | Next.js 15, React 19, TypeScript, Recharts, Tailwind |
| **Backend API** | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.x |
| **Database** | PostgreSQL 15+ |
| **Cache & Jobs** | Redis 7+ (background replay processing) |
| **Analysis** | pandas, NumPy, scikit-learn |
| **Replay Parsing** | aoc-mgz or equivalent |
| **ML (future)** | XGBoost, LightGBM, PyTorch |
| **Containerization** | Docker Compose |
| **Testing** | pytest, Playwright, Vitest |

### Directory Structure

```
frontend/              # Next.js + React + TypeScript
  ├── app/
  ├── components/
  ├── lib/
  └── tests/

backend/               # Python + FastAPI
  ├── app/
  │   ├── api/v1/      # API endpoints
  │   ├── core/        # Config, logging, errors
  │   ├── db/          # Database setup
  │   ├── schemas/     # Pydantic models
  │   ├── services/    # Business logic
  │   │   ├── aoe/           # AoE2 domain (parser, events)
  │   │   ├── replay/        # Replay ingestion & state
  │   │   ├── analytics/     # Metric calculations
  │   │   ├── feature_eng/   # Feature engineering
  │   │   └── ml/            # ML models
  │   ├── workers/     # Background jobs
  │   └── cli.py
  ├── alembic/         # Database migrations
  └── tests/

infra/
  └── docker-compose.yml
```

### Database Schema

**Core Tables:**
- `players` — username, Elo bands, civ win rates
- `matches` — map, duration, patch, winner
- `match_players` — player per match, civ, team, result
- `replay_files` — uploaded replay, hash, parse status

**Analysis Tables:**
- `events` — normalized event stream (AGE_UP, BUILD, UNIT_DIED, etc.)
- `game_states` — snapshots every 5-15s per player
- `engagements` — identified fights with participants, value, outcome
- `economy_snapshots` — periodic economy state (resources, villagers, production)
- `military_snapshots` — periodic military state (composition, value, production)

**Metrics & Models:**
- `match_metrics` — all derived metrics for a match
- `player_metric_percentiles` — peer comparison (Elo-conditioned)
- `model_versions` — ML model tracking
- `coaching_insights` — per-match coaching report

---

## Data & Privacy

**Scope:** Analysis is retrospective only, over match history and replay data that the player can already access.

**Assumptions:**
- Replay files are provided by the player or are from public sources
- No live-game or spectator integration
- No hidden enemy information used in models
- All model outputs clearly marked as estimates with confidence ranges

---

## Metrics Definitions

### Methodology
- **Directly observed:** Count from parsed replay (e.g., TC idle time in milliseconds)
- **Reconstructed:** Estimated from event stream with clear assumptions (e.g., resource float)
- **Inferred:** Derived from multiple observations (e.g., scouting efficiency score)
- **ML-estimated:** Model output with confidence; association not causation (e.g., skill gap)

### Key Metrics

| Metric | Type | Definition |
| --- | --- | --- |
| TC Idle Time | Observed | Milliseconds TC spent not producing villagers (feudal+) |
| Resource Float | Reconstructed | Sum of unspent resources from last collection/tribute event |
| Age-Up Timing Delta | Observed | Difference vs. median for civ/map/opening cohort |
| Engagement Efficiency | Inferred | (Army value × kill ratio) / time_elapsed; normalized by civ |
| Scouting Coverage | Reconstructed | Fraction of map fogged over time; estimated from unit movements |
| Reaction Latency | Observed | Time between opponent action visibility and counter-response |
| Skill Gap Score | ML-estimated | SHAP-based feature importance separating Elo tiers |
| Decision Value Added | ML-estimated | Expected outcome vs. realized outcome from comparable states |

---

## Development Workflow

### Adding a New Metric

1. Create calculation function in `backend/app/services/analytics/`
2. Add Pydantic schema in `backend/app/schemas/`
3. Integrate into match analysis pipeline
4. Write tests with sample replay data
5. Update frontend dashboard if user-facing

### Processing a Replay

```python
# Backend pipeline
1. POST /api/v1/replays/upload → store file, queue job
2. Worker picks up job → parse with aoc-mgz
3. Extract metadata → store in DB
4. Normalize event stream
5. Reconstruct game states (snapshots)
6. Calculate all metrics
7. Run ML models
8. Generate coaching insights
9. Mark analysis complete
```

### Frontend Displays

```
Landing → Search/Upload → Player Dashboard
                               ↓
                         Match List → Match Analysis
                                         ├── Economy Dashboard
                                         ├── Military Dashboard
                                         ├── Build Timeline
                                         ├── Engagement Map
                                         └── Coaching Report
```

---

## Testing

```bash
# Run all tests
make test

# Run specific test module
pytest backend/tests/test_analytics.py -v

# Test with coverage
pytest --cov=backend/app backend/tests/
```

Test fixtures include:
- Sample replay files (`.aoe2record`)
- Mock parsed event streams
- Synthetic match histories
- Peer cohort data for comparison

---

## Deployment & Production

### Environment Variables

See `.env.example`. Key settings:

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/aoe2

# Redis (job queue)
REDIS_URL=redis://localhost:6379/0

# Logging
LOG_LEVEL=INFO
ENVIRONMENT=production

# Replay parsing
REPLAY_PARSER_TIMEOUT=300  # seconds
MAX_REPLAY_SIZE_MB=100

# Feature flags
ENABLE_ML_MODELS=true
ENABLE_PLAYER_STATS=true
```

### Docker Compose Deployment

```bash
docker compose -f docker-compose.yml up -d

# Verify services
docker compose ps
curl http://localhost:8000/health
```

### Database Migrations

Migrations run automatically on startup. Manual:

```bash
cd backend
alembic upgrade head
```

---

## Roadmap

### MVP (Current)
- ✅ Replay upload & parsing
- ✅ Event normalization
- ✅ State reconstruction
- ✅ Core metric calculations
- ✅ Match timeline UI
- ✅ Peer comparison
- ✅ Coaching report

### Phase 2
- [ ] Skill gap analysis (ML)
- [ ] Decision value modeling
- [ ] Win probability curves
- [ ] Player archetyping
- [ ] Advanced interactive timeline

### Phase 3+
- [ ] Public match auto-discovery
- [ ] Streamer integration (live analysis)
- [ ] Tournament replay analysis
- [ ] API client for third-party tools
- [ ] Player comparison tools
- [ ] Team analysis

---

## Contributing

See `CONTRIBUTING.md` for development guidelines.

---

## License

MIT. See `LICENSE`.

---

## Acknowledgments

- Replay parsing: [aoc-mgz](https://github.com/happyleavesaoc/aoc-mgz) and community
- Architecture inspired by sports analytics and esports coaching platforms
- Built with ❤️ for the RTS community
