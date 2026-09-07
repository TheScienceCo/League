"""End-to-end Skill Gap: does the model recover structure we know is there?

This is the methodology's self-check. The simulator generates players whose
latent skill drives specific observable behaviours (farm rate, damage output,
vision, positional risk) and *not* others. A correct pipeline should rank those
behaviours highly and should order players by rank far better than chance.

It says nothing about real League of Legends — only that the machinery works.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app.core.constants import TIER_GROUP_ORDER
from app.core.errors import InsufficientDataError
from app.db.models import ParticipantFeatures
from app.services.analytics.cohorts import refresh_cohorts
from app.services.ingest.pipeline import IngestionService, IngestOptions
from app.services.ml.skill_gap import (
    analyze_player,
    next_tier_group,
    rank_separation_summary,
    train_skill_gap_model,
)
from app.services.riot.mock import MockRiotProvider
from app.services.riot.simulation import rank_for_skill, skill_for_puuid
from tests.conftest import scope_for

#: This module ingests a rank-spanning corpus and trains a real model, so it is
#: minutes rather than seconds. Excluded from the default run; CI runs it with
#: `pytest -m slow`.
pytestmark = pytest.mark.slow

#: Behaviours the simulator ties to latent skill. The model should lean on these.
SKILL_DRIVEN = {
    "cs_per_min",
    "cs_per_min_first_15",
    "damage_per_min",
    "damage_per_gold",
    "vision_score_per_min",
    "wards_placed_per_min",
    "mean_position_risk",
}


@pytest.fixture(scope="module")
def corpus_db():  # type: ignore[no-untyped-def]
    """A rank-spanning corpus, built once for the whole module."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.models import Base

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    provider = MockRiotProvider()
    service = IngestionService(provider, session_scope=scope_for(session))

    # Pick accounts spanning every rank band so the model has something to
    # separate. Scanning for them keeps the spread deterministic.
    buckets: dict[str, list[str]] = {band: [] for band in TIER_GROUP_ORDER}
    from app.core.constants import tier_group
    from app.services.riot.mock import mock_puuid_for

    for i in range(2000):
        if all(len(v) >= 2 for v in buckets.values()):
            break
        name = f"Corpus{i:04d}"
        tier, _, _ = rank_for_skill(skill_for_puuid(mock_puuid_for(name, "NA1")))
        band = tier_group(tier)
        if band in buckets and len(buckets[band]) < 2:
            buckets[band].append(f"{name}#NA1")

    async def build() -> None:
        for riot_ids in buckets.values():
            for riot_id in riot_ids:
                puuid = await service.resolve_riot_id(riot_id, "na1")
                await service.ingest_player(
                    puuid,
                    "na1",
                    IngestOptions(count=8, resolve_participant_ranks=True, concurrency=4),
                )

    asyncio.run(build())
    session.flush()
    refresh_cohorts(session, min_n=20)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture(scope="module")
def trained(corpus_db):  # type: ignore[no-untyped-def]
    """Train once; every assertion below reads the same artifact.

    Retraining per test would multiply the module's cost by the number of tests
    without testing anything new.
    """
    return train_skill_gap_model(corpus_db, min_rows=200)


def test_corpus_spans_every_rank_band(corpus_db) -> None:  # type: ignore[no-untyped-def]
    bands = {r.tier_group for r in corpus_db.scalars(select(ParticipantFeatures))} - {"UNRANKED"}
    assert bands == set(TIER_GROUP_ORDER)


def test_model_orders_players_by_rank_far_better_than_chance(trained) -> None:  # type: ignore[no-untyped-def]
    metrics = trained.metrics

    assert metrics["n_tier_bands"] == 5
    # Cross-validated with players never split across folds, so this is not
    # memorisation of individual accounts.
    assert metrics["cv_rank_spearman"] > 0.5, metrics
    assert metrics["cv_balanced_accuracy"] > metrics["chance_balanced_accuracy"] * 1.5


def test_model_recovers_the_planted_behaviours(trained) -> None:  # type: ignore[no-untyped-def]
    """The top of the importance ranking should be behaviours skill drives."""
    artifact = trained
    top5 = [
        feature
        for feature, _ in sorted(
            artifact.feature_importances.items(), key=lambda kv: kv[1], reverse=True
        )[:5]
    ]
    assert SKILL_DRIVEN & set(top5), f"expected skill-driven behaviours, got {top5}"


def test_rank_correlations_have_the_expected_sign(trained) -> None:  # type: ignore[no-untyped-def]
    correlations = trained.metrics["rank_correlations"]

    # Better players farm and deal damage more; they also die less.
    assert correlations["cs_per_min"] > 0.3
    assert correlations["damage_per_min"] > 0.3
    assert correlations["vision_score_per_min"] > 0.2
    assert correlations["deaths_per_10min"] < 0.1


def test_player_report_is_well_formed(corpus_db, trained) -> None:  # type: ignore[no-untyped-def]
    puuid = corpus_db.scalar(
        select(ParticipantFeatures.puuid).where(ParticipantFeatures.tier_group != "UNRANKED")
    )
    report = analyze_player(corpus_db, puuid, top_n=5)

    assert report.puuid == puuid
    assert report.player_tier_group in TIER_GROUP_ORDER
    assert len(report.behaviours) <= 5
    assert report.caveats, "a model-derived report must carry its caveats"
    assert any("causal" in c.lower() or "association" in c.lower() for c in report.caveats)

    for behaviour in report.behaviours:
        assert behaviour.label
        assert 0.0 <= behaviour.importance <= 1.0
        assert behaviour.impact >= 0.0
        # impact is importance x the positive part of the gap.
        assert behaviour.impact == pytest.approx(
            behaviour.importance * max(behaviour.gap_z, 0.0), abs=1e-9
        )

    # Behaviours are ranked by impact, descending.
    impacts = [b.impact for b in report.behaviours]
    assert impacts == sorted(impacts, reverse=True)


def test_target_defaults_to_the_next_band_up(corpus_db, trained) -> None:  # type: ignore[no-untyped-def]
    puuid = corpus_db.scalar(
        select(ParticipantFeatures.puuid).where(ParticipantFeatures.tier_group == "SILVER_GOLD")
    )
    report = analyze_player(corpus_db, puuid)
    assert report.target_tier_group == next_tier_group(report.player_tier_group)


def test_next_tier_group_saturates_at_the_top() -> None:
    assert next_tier_group("IRON_BRONZE") == "SILVER_GOLD"
    assert next_tier_group("MASTER_PLUS") == "MASTER_PLUS"
    assert next_tier_group("UNRANKED") == TIER_GROUP_ORDER[0]


def test_rank_separation_summary_is_ordered(corpus_db, trained) -> None:  # type: ignore[no-untyped-def]
    summary = rank_separation_summary(corpus_db, top_n=10)

    assert summary["model"]["n_samples"] > 0
    importances = [b["importance"] for b in summary["behaviours"]]
    assert importances == sorted(importances, reverse=True)
    for behaviour in summary["behaviours"]:
        assert behaviour["tier_means"], "tier means drive the UI's comparison chart"


def test_training_refuses_rather_than_guessing_on_thin_data(db) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(InsufficientDataError):
        train_skill_gap_model(db, min_rows=200)
