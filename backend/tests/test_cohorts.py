"""Cohort baselines, fallback behaviour, and per-game player summaries."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models import Match, ParticipantFeatures
from app.services.analytics.cohorts import (
    COHORT_LEVELS,
    CohortService,
    cohort_key,
    game_context,
    refresh_cohorts,
)


def _feature(
    db,  # type: ignore[no-untyped-def]
    *,
    match_id: str,
    puuid: str,
    cs_per_min: float,
    role: str = "MIDDLE",
    champion_id: int = 103,
    tier_group: str = "PLAT_EMERALD",
    patch: str = "14.19",
    duration_bucket: str = "MEDIUM",
) -> None:
    if db.get(Match, match_id) is None:
        db.add(
            Match(
                match_id=match_id,
                platform="na1",
                region="americas",
                queue_id=420,
                patch=patch,
                game_start=datetime.now(UTC),
                game_duration_seconds=1800,
                winning_team_id=100,
            )
        )
    db.add(
        ParticipantFeatures(
            match_id=match_id,
            puuid=puuid,
            participant_id=1,
            team_position=role,
            champion_id=champion_id,
            tier_group=tier_group,
            rank_score=1800.0,
            patch=patch,
            queue_id=420,
            duration_bucket=duration_bucket,
            duration_seconds=1800,
            win=True,
            cs_per_min=cs_per_min,
        )
    )


def _populate(db, n: int = 40, **kwargs) -> None:  # type: ignore[no-untyped-def]
    for i in range(n):
        _feature(db, match_id=f"M{i}", puuid=f"pop{i}", cs_per_min=5.0 + i * 0.05, **kwargs)
    db.flush()


def test_cohort_key_is_order_independent() -> None:
    assert cohort_key({"a": 1, "b": 2}) == cohort_key({"b": 2, "a": 1})
    assert cohort_key({"a": 1}) != cohort_key({"a": 2})


def test_refresh_builds_every_specificity_level(db) -> None:  # type: ignore[no-untyped-def]
    _populate(db, 40)
    written = refresh_cohorts(db, metrics=["cs_per_min"], min_n=20)
    assert written > 0

    from app.db.models import CohortStat

    specificities = {c.specificity for c in db.query(CohortStat).all()}
    # Every level in the chain is populated because one homogeneous group
    # satisfies all of them.
    assert len(specificities) == len(COHORT_LEVELS)


def test_sparse_cohorts_are_not_written(db) -> None:  # type: ignore[no-untyped-def]
    _populate(db, 5)
    assert refresh_cohorts(db, metrics=["cs_per_min"], min_n=20) == 0


def test_lookup_falls_back_to_a_broader_cohort(db) -> None:  # type: ignore[no-untyped-def]
    """A champion we have never seen must not silently produce no comparison."""
    _populate(db, 40)
    refresh_cohorts(db, metrics=["cs_per_min"], min_n=20)
    service = CohortService(db, min_n=20)

    exact = service.resolve_detail(
        "cs_per_min",
        {
            "team_position": "MIDDLE",
            "champion_id": 103,
            "tier_group": "PLAT_EMERALD",
            "patch": "14.19",
            "duration_bucket": "MEDIUM",
        },
    )
    assert exact is not None
    assert exact.is_fallback is False

    unseen = service.resolve_detail(
        "cs_per_min",
        {
            "team_position": "MIDDLE",
            "champion_id": 999999,  # never played
            "tier_group": "PLAT_EMERALD",
            "patch": "14.19",
            "duration_bucket": "MEDIUM",
        },
    )
    assert unseen is not None, "should fall back rather than return nothing"
    assert unseen.is_fallback is True
    # The fallback dropped the champion dimension.
    assert "champion_id" not in unseen.stat.dimensions


def test_percentiles_track_the_distribution(db) -> None:  # type: ignore[no-untyped-def]
    _populate(db, 40)
    refresh_cohorts(db, metrics=["cs_per_min"], min_n=20)
    service = CohortService(db, min_n=20)
    context = {
        "team_position": "MIDDLE",
        "champion_id": 103,
        "tier_group": "PLAT_EMERALD",
        "patch": "14.19",
        "duration_bucket": "MEDIUM",
    }
    low = service.compare("cs_per_min", 5.0, context)
    mid = service.compare("cs_per_min", 6.0, context)
    high = service.compare("cs_per_min", 7.0, context)
    assert low and mid and high
    assert low.percentile < mid.percentile < high.percentile
    assert 0 < low.percentile <= 100 and 0 < high.percentile <= 100


def test_game_context_is_always_internally_coherent(db) -> None:  # type: ignore[no-untyped-def]
    _feature(db, match_id="X1", puuid="p", cs_per_min=6.0, role="BOTTOM", champion_id=222)
    db.flush()
    row = db.query(ParticipantFeatures).one()
    context = game_context(row)
    assert context == {
        "team_position": "BOTTOM",
        "champion_id": 222,
        "tier_group": "PLAT_EMERALD",
        "patch": "14.19",
        "duration_bucket": "MEDIUM",
    }


def test_player_summary_uses_each_games_own_cohort(db) -> None:  # type: ignore[no-untyped-def]
    """A multi-game mean must not be scored against a single-game distribution.

    The player below is dead-average in every game, so their summary percentile
    should sit near the middle — not in a tail, which is what comparing a mean
    against the per-game spread would produce.
    """
    _populate(db, 60)
    refresh_cohorts(db, metrics=["cs_per_min"], min_n=20)

    for i in range(8):
        _feature(db, match_id=f"MINE{i}", puuid="me", cs_per_min=6.0 + (0.4 if i % 2 else -0.4))
    db.flush()

    rows = db.query(ParticipantFeatures).filter(ParticipantFeatures.puuid == "me").all()
    summary = CohortService(db, min_n=20).summarize_player(rows, "cs_per_min")
    assert summary is not None
    assert summary.games_compared == 8
    assert summary.value == pytest.approx(6.0)
    assert 25 < summary.percentile < 75


def test_rce_normalisation_is_a_cohort_z_score(db) -> None:  # type: ignore[no-untyped-def]
    from app.services.analytics.cohorts import normalize_rce

    for i in range(40):
        _feature(db, match_id=f"R{i}", puuid=f"r{i}", cs_per_min=6.0)
        db.flush()
    # Give every row an RCE so a cohort exists, then one clear outlier.
    for idx, row in enumerate(db.query(ParticipantFeatures).all()):
        row.rce_raw = 1.0 + (idx % 5) * 0.05
    db.flush()

    refresh_cohorts(db, metrics=["rce_raw"], min_n=20)
    assert normalize_rce(db, min_n=20) > 0

    values = [r.rce_z for r in db.query(ParticipantFeatures).all() if r.rce_z is not None]
    assert values
    # A z-score set is centred near zero.
    assert abs(sum(values) / len(values)) < 0.5
