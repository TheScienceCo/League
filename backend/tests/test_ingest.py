"""End-to-end ingestion through the real pipeline against the simulator."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db.models import (
    LeagueEntry,
    Match,
    MatchParticipant,
    MatchTeam,
    ObjectiveSetup,
    ParticipantFeatures,
    RoamEvent,
    Summoner,
    TimelineEvent,
    TimelineFrame,
)


def _count(db, model) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_ingest_populates_every_layer(seeded_db) -> None:  # type: ignore[no-untyped-def]
    db = seeded_db
    assert _count(db, Summoner) > 3, "participants should be resolved too"
    assert _count(db, LeagueEntry) > 0
    assert _count(db, Match) >= 3
    assert _count(db, MatchTeam) == _count(db, Match) * 2
    assert _count(db, MatchParticipant) == _count(db, Match) * 10
    assert _count(db, TimelineFrame) > 0
    assert _count(db, TimelineEvent) > 0
    # Derived layers.
    assert _count(db, ParticipantFeatures) == _count(db, Match) * 10
    assert _count(db, ObjectiveSetup) > 0


def test_every_match_is_summoners_rift_ranked(seeded_db) -> None:  # type: ignore[no-untyped-def]
    for match in seeded_db.scalars(select(Match)):
        assert match.queue_id == 420
        assert match.timeline_ingested is True
        assert match.features_computed is True
        assert match.winning_team_id in (100, 200)
        assert match.patch.count(".") == 1


def test_frames_are_unique_per_participant_and_timestamp(seeded_db) -> None:  # type: ignore[no-untyped-def]
    duplicates = seeded_db.execute(
        select(
            TimelineFrame.match_id,
            TimelineFrame.participant_id,
            TimelineFrame.timestamp_ms,
            func.count(),
        )
        .group_by(
            TimelineFrame.match_id,
            TimelineFrame.participant_id,
            TimelineFrame.timestamp_ms,
        )
        .having(func.count() > 1)
    ).all()
    assert duplicates == []


def test_ranks_are_attached_to_participants(seeded_db) -> None:  # type: ignore[no-untyped-def]
    ranked = seeded_db.scalar(
        select(func.count())
        .select_from(MatchParticipant)
        .where(MatchParticipant.tier_group != "UNRANKED")
    )
    total = _count(seeded_db, MatchParticipant)
    # With participant rank resolution on, nearly everyone should be placed.
    assert ranked / total > 0.9


def test_features_are_populated_not_null(seeded_db) -> None:  # type: ignore[no-untyped-def]
    rows = list(seeded_db.scalars(select(ParticipantFeatures)))
    assert rows
    assert all(r.cs_per_min > 0 for r in rows)
    assert all(r.damage_per_gold > 0 for r in rows)
    # Shares are proportions.
    for r in rows:
        if r.damage_share is not None:
            assert 0.0 <= r.damage_share <= 1.0
        if r.gold_share is not None:
            assert 0.0 <= r.gold_share <= 1.0
        if r.kill_participation is not None:
            assert 0.0 <= r.kill_participation <= 1.0


def test_rce_equals_damage_share_over_gold_share(seeded_db) -> None:  # type: ignore[no-untyped-def]
    for r in seeded_db.scalars(select(ParticipantFeatures)):
        if r.rce_raw is not None and r.damage_share and r.gold_share:
            assert r.rce_raw == pytest.approx(r.damage_share / r.gold_share, rel=1e-6)


def test_roams_exclude_junglers(seeded_db) -> None:  # type: ignore[no-untyped-def]
    roles = {r.role for r in seeded_db.scalars(select(RoamEvent))}
    assert "JUNGLE" not in roles


def test_reingestion_is_idempotent(seeded_db, provider) -> None:  # type: ignore[no-untyped-def]
    """Running the same job twice must not duplicate anything."""
    import asyncio

    from app.services.ingest import pipeline as pipeline_module
    from tests.conftest import scope_for

    db = seeded_db
    before = {
        m: _count(db, m) for m in (Match, MatchParticipant, TimelineFrame, ParticipantFeatures)
    }
    service = pipeline_module.IngestionService(provider, session_scope=scope_for(db))

    async def run() -> None:
        puuid = await service.resolve_riot_id("TestAlpha#NA1", "na1")
        result = await service.ingest_player(
            puuid, "na1", pipeline_module.IngestOptions(count=4, concurrency=1)
        )
        # Everything was already stored, so nothing new is ingested.
        assert result.ingested == 0
        assert result.skipped == 4

    asyncio.run(run())
    db.flush()

    after = {
        m: _count(db, m) for m in (Match, MatchParticipant, TimelineFrame, ParticipantFeatures)
    }
    assert before == after


def test_force_refresh_replaces_rather_than_duplicates(seeded_db, provider) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    from app.services.ingest import pipeline as pipeline_module
    from tests.conftest import scope_for

    db = seeded_db
    before = {
        m: _count(db, m) for m in (Match, MatchParticipant, TimelineFrame, ParticipantFeatures)
    }
    service = pipeline_module.IngestionService(provider, session_scope=scope_for(db))

    async def run() -> None:
        puuid = await service.resolve_riot_id("TestAlpha#NA1", "na1")
        await service.ingest_player(
            puuid,
            "na1",
            pipeline_module.IngestOptions(count=4, concurrency=1, force_refresh=True),
        )

    asyncio.run(run())
    db.flush()
    assert {m: _count(db, m) for m in before} == before
