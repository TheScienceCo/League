"""Rank scoring, routing, patches and duration buckets."""

from __future__ import annotations

import pytest

from app.core.constants import (
    APEX_TIERS,
    TIER_GROUP_ORDER,
    TIER_ORDER,
    Phase,
    duration_bucket,
    parse_patch,
    phase_for_seconds,
    region_for_platform,
    tier_group,
    tier_rank_score,
)


def test_rank_score_is_monotone_across_tiers() -> None:
    scores = [tier_rank_score(tier, "IV", 0) for tier in TIER_ORDER]
    assert scores == sorted(scores)
    # Every tier below Master is strictly separated; the three apex tiers share a
    # base by design and are separated by LP instead.
    below_apex = [tier_rank_score(t, "IV", 0) for t in TIER_ORDER if t not in APEX_TIERS]
    assert len(set(below_apex)) == len(below_apex)
    assert max(below_apex) < tier_rank_score("MASTER", None, 0)


def test_rank_score_orders_divisions_within_a_tier() -> None:
    assert (
        tier_rank_score("GOLD", "IV", 0)
        < tier_rank_score("GOLD", "III", 0)
        < tier_rank_score("GOLD", "II", 0)
        < tier_rank_score("GOLD", "I", 0)
    )


def test_apex_tiers_are_ordered_by_lp_alone() -> None:
    """Master/GM/Challenger are one LP ladder, not three stacked tiers.

    A 2000 LP Master really is ahead of a 1200 LP Challenger on the ladder, and
    the score has to reflect that or every rank-conditioned comparison inherits
    the error.
    """
    assert tier_rank_score("MASTER", None, 500) > tier_rank_score("MASTER", None, 100)
    assert tier_rank_score("MASTER", None, 0) == tier_rank_score("CHALLENGER", None, 0)
    assert tier_rank_score("MASTER", None, 2000) > tier_rank_score("CHALLENGER", None, 1200)
    assert tier_rank_score("CHALLENGER", None, 1500) > tier_rank_score("GRANDMASTER", None, 800)


def test_rank_score_handles_missing_input() -> None:
    assert tier_rank_score(None) == 0.0
    assert tier_rank_score("NOT_A_TIER", "IV", 0) == 0.0


def test_tier_groups_cover_every_tier_and_stay_ordered() -> None:
    groups = [tier_group(tier) for tier in TIER_ORDER]
    assert set(groups) == set(TIER_GROUP_ORDER)
    # Group order must follow tier order.
    indices = [TIER_GROUP_ORDER.index(g) for g in groups]
    assert indices == sorted(indices)
    assert tier_group(None) == "UNRANKED"


@pytest.mark.parametrize(
    ("platform", "region"),
    [("na1", "americas"), ("euw1", "europe"), ("kr", "asia"), ("oc1", "sea"), ("NA1", "americas")],
)
def test_platform_routing(platform: str, region: str) -> None:
    assert region_for_platform(platform) == region


def test_unknown_platform_raises() -> None:
    with pytest.raises(ValueError):
        region_for_platform("mars1")


@pytest.mark.parametrize(
    ("version", "patch"),
    [("14.19.624.1234", "14.19"), ("15.1.1.1", "15.1"), (None, "unknown"), ("weird", "unknown")],
)
def test_patch_parsing(version: str | None, patch: str) -> None:
    assert parse_patch(version) == patch


def test_duration_buckets_partition_the_range() -> None:
    assert duration_bucket(10 * 60) == "SHORT"
    assert duration_bucket(28 * 60) == "MEDIUM"
    assert duration_bucket(40 * 60) == "LONG"
    # Boundaries belong to the upper bucket.
    assert duration_bucket(25 * 60) == "MEDIUM"
    assert duration_bucket(32 * 60) == "LONG"


def test_phase_boundaries() -> None:
    assert phase_for_seconds(0) is Phase.EARLY
    assert phase_for_seconds(14 * 60 - 1) is Phase.EARLY
    assert phase_for_seconds(14 * 60) is Phase.MID
    assert phase_for_seconds(25 * 60) is Phase.LATE
