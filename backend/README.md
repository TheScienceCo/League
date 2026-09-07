# Rift Lab — backend

FastAPI service, ingestion pipeline, analytics and ML for the Rift Lab platform.
See the [repository README](../README.md) for setup and the
[architecture notes](../docs/ARCHITECTURE.md) for how the pieces fit together.

```
app/
  api/          HTTP layer — routers, dependencies, no business logic
  core/         config, logging, errors, domain constants
  db/           SQLAlchemy models, session management, portable column types
  schemas/      Pydantic response models
  services/
    riot/       Riot API client, the RiotProvider protocol, and the simulator
    ingest/     the pipeline: payloads -> normalized rows -> features
    analytics/  derived metrics, cohorts, spatial risk, roams, objectives, DVA
    ml/         residualization, model registry, Skill Gap Analysis
  cli.py        `riftlab` operational commands
alembic/        migrations
tests/          pytest suite (SQLite by default; no containers needed)
```

## Commands

```bash
riftlab ingest 'Name#TAG' --count 30   # ingest one player's matches
riftlab seed --accounts 40 --matches 16 # build a demo corpus (simulator only)
riftlab refresh-analytics               # rebuild cohorts, risk surface, models
riftlab skill-gap 'Name#TAG'            # print a Skill Gap report
```
