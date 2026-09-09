# AoE2 Lab

Upload an Age of Empires II: Definitive Edition replay and get your age timings
against your opponent's, a curve of everything you left unspent, your build
order, and observations that each cite a number that was actually measured.

```bash
cp .env.example .env
docker compose up --build
# then open http://localhost:3000 and drop in an .aoe2record file
```

Or without Docker: `make install && make api` in one shell, `make web` in
another. Analysing a replay from the command line:

```bash
make analyse REC=~/Games/AoE2DE/SaveGame/rec.aoe2record
```

---

## The one thing to understand

**A replay is a command stream, not a match report.** An `.aoe2record` file
stores the inputs players sent to the engine — move here, build there, research
this — with the tick each was sent on. Replaying those inputs against the same
engine reproduces the game, which is how the in-game viewer works.

So the file records *what players did*, not *what happened*. "Queued a villager
at 4:32" is in there. "A villager was created" is not, because the queue can be
cancelled or the Town Center destroyed. **Unit deaths, kills and combat outcomes
are absent from the file entirely.**

This shapes the whole product. There is no kill/death ratio here and no
"resources destroyed" figure, because there is no honest way to compute one.
Those metrics report `unavailable` — never `0`, which would read as a
measurement of nothing.

Every metric carries how it was obtained:

| | |
|---|---|
| `observed` | Read directly out of the command stream. Exact. |
| `reconstructed` | Derived from observed commands under a stated assumption. |
| `inferred` | From DE sync packets, whose field meanings are community reverse-engineered rather than documented. Directionally right, not exact. |
| `unavailable` | Not recoverable. The value is `null`. |

---

## What it measures

| Metric | Provenance | Notes |
|---|---|---|
| Feudal / Castle / Imperial reached | `observed` | From the game's own age transitions — the most reliable figure in the file |
| Age timing vs opponent | `observed` | Gap to the fastest other player; negative is faster |
| Average / peak banked resources | `inferred` | All four resources combined; no per-type split is transmitted |
| Time above 1000 banked | `inferred` | Roughly a Town Center's worth left unspent |
| Banked resources per age | `inferred` | Which phase you were least efficient in |
| Longest villager-queue gap | `reconstructed` | A proxy for TC idle time; a batched queue can mask a real gap |
| Villagers queued | `observed` | Queue commands, not completed villagers |
| Buildings placed / techs researched | `observed` | Counts intent; a foundation can be cancelled |
| Effective APM | `observed` | Spam and duplicate orders excluded |
| Opening | `reconstructed` | Four recognised cases; reports `unclassified` rather than guessing |
| Resources killed / lost, engagement efficiency | `unavailable` | Not in the file. See above. |

### When parsing degrades

Action encodings change between game versions and the parser does not decode
every one. Three cases are handled explicitly rather than papered over:

- **Unit-queue commands don't decode** on some versions. Production metrics then
  report `unavailable` and the response carries a warning, instead of claiming
  you queued zero villagers.
- **A large share of actions don't decode** (>25%): build-order detail is flagged
  as incomplete.
- **The file won't parse at all** (older versions): rejected with an explanation,
  not a generic 500.

---

## Architecture

```
frontend/                Next.js 16, React 19, TypeScript, Recharts
backend/
  app/
    api/v1/              health, replays
    core/                config, logging, errors
    db/                  models, session
    schemas/             API contracts
    services/
      parser/            the ONLY place that imports mgz
      analysis/          metrics, insights, store, persistence
  alembic/               migrations
  tests/fixtures/        real .aoe2record files
```

**The parser seam.** Everything downstream depends on the `ReplayParser`
Protocol and the dataclasses beside it, never on `mgz`. Swapping the parsing
library means implementing that Protocol and nothing else.

**ID resolution.** Object and technology IDs resolve through the `aocref`
dataset rather than hardcoded tables, because one logical entity has many IDs —
a Town Center is 71, 109, 141, 142, 481–484, 597 and 611–621 depending on
civilisation, age and graphic variant. Grouping by resolved *name* is the only
stable way to ask "is this a Town Center?".

**Storage.** An analysis is a self-contained document written once and read
whole, so it lives as JSON on disk keyed by the SHA-256 of the replay. Postgres
holds an index of it — who played, what they picked, when they aged up — for
questions that span many replays. Indexing is best-effort: a database outage
cannot fail an upload, because nothing about parsing needs one.

**Determinism.** The same file always produces the same analysis. Nothing
samples, randomises, or reads a clock.

---

## Development

```bash
make install     # backend venv
make test        # 46 tests, ~16s, no containers needed
make lint        # ruff + mypy + tsc
make api         # API on :8000
make web         # frontend on :3000
```

Tests run against **real replay files** in `backend/tests/fixtures/`, not
synthetic bytes — the entire risk in this codebase is mis-reading a real file
format. The three fixtures are chosen to cover distinct parser paths: one where
queue commands decode, one where they don't, and one too old to parse at all.
They come from [aoc-mgz](https://github.com/happyleavesaoc/aoc-mgz) (MIT).

---

## Not built yet

Being straight about it, since an earlier version of this README was not:

- **Peer comparison against an Elo cohort** — the schema is shaped for it, but
  it needs a corpus of analysed games first.
- **Scouting and map-control metrics** — plausible from `MOVE`/`ORDER`
  positions, not attempted.
- **Engagement detection** — bounded by the command-stream limit above. It could
  only ever be inferred from unit movement, and would have to say so.
- **Any model-based skill estimate** — nothing here is ML. The `ml` extra in
  `pyproject.toml` is a declaration of intent, not a wired-up dependency.

---

## Credits

Replay parsing by [aoc-mgz](https://github.com/happyleavesaoc/aoc-mgz).
Not endorsed by or affiliated with Microsoft or Xbox Game Studios.
