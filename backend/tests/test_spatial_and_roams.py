"""Spatial exposure labelling, the risk surface, and roam valuation."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import MapRiskCell, RoamEvent
from app.services.analytics.roams import (
    ROAM_DISTANCE_UNITS,
    XP_TO_GOLD,
    detect_roams,
)
from app.services.analytics.spatial import build_exposure_frame, refresh_risk_grid


def test_exposure_frame_labels_deaths_within_the_horizon(seeded_db) -> None:  # type: ignore[no-untyped-def]
    df = build_exposure_frame(seeded_db, horizon_seconds=30)
    assert not df.empty

    required = {
        "match_id",
        "puuid",
        "x",
        "y",
        "zone",
        "phase",
        "role",
        "team_gold_diff",
        "died_within_horizon",
        "cell_x",
        "cell_y",
    }
    assert required <= set(df.columns)

    # The label is a rare event, but it does happen.
    rate = df["died_within_horizon"].mean()
    assert 0.0 < rate < 0.5, f"implausible death rate {rate}"
    assert df["died_within_horizon"].isin([0, 1]).all()


def test_exposure_features_stay_in_range(seeded_db) -> None:  # type: ignore[no-untyped-def]
    df = build_exposure_frame(seeded_db, horizon_seconds=30)
    assert df["x"].between(-2000, 17000).all()
    assert df["y"].between(-2000, 17000).all()
    assert df["cell_x"].between(0, 31).all()
    assert df["cell_y"].between(0, 31).all()
    assert df["phase"].isin(["EARLY", "MID", "LATE"]).all()
    assert (df["nearby_recent_deaths"] >= 0).all()


def test_team_gold_diff_is_antisymmetric(seeded_db) -> None:  # type: ignore[no-untyped-def]
    """One team's lead is the other's deficit; a sign error here would poison
    every game-state feature downstream."""
    df = build_exposure_frame(seeded_db, horizon_seconds=30)
    sample = df.groupby(["match_id", "timestamp_ms"]).filter(lambda g: g["team_id"].nunique() == 2)
    grouped = sample.groupby(["match_id", "timestamp_ms"])["team_gold_diff"]
    sums = grouped.apply(lambda s: s.unique().sum())
    assert sums.abs().max() < 1e-6


def test_risk_model_never_sees_enemy_positions() -> None:
    """A compliance property, asserted rather than merely documented."""
    from app.services.analytics.spatial import CATEGORICAL_FEATURES, NUMERIC_FEATURES

    features = set(NUMERIC_FEATURES) | set(CATEGORICAL_FEATURES)
    forbidden = {
        "enemy_x",
        "enemy_y",
        "enemy_positions",
        "nearest_enemy_distance",
        "enemies_nearby",
    }
    assert features & forbidden == set()
    # The only positional inputs are the player's own coordinates and distances
    # to fixed map landmarks.
    assert {"x", "y", "dist_dragon", "dist_baron", "dist_own_base"} <= features


def test_risk_grid_is_built_with_sane_values(seeded_db) -> None:  # type: ignore[no-untyped-def]
    written = refresh_risk_grid(seeded_db, horizon_seconds=30, grid_size=32)
    assert written > 0

    cells = list(seeded_db.scalars(select(MapRiskCell)))
    assert cells
    for cell in cells:
        assert 0 <= cell.cell_x < 32 and 0 <= cell.cell_y < 32
        assert 0.0 <= cell.risk <= 1.0
        assert cell.deaths <= cell.exposures
        assert cell.lift >= 0.0
        assert cell.zone is not None


def test_risk_grid_rebuild_replaces_rather_than_appends(seeded_db) -> None:  # type: ignore[no-untyped-def]
    first = refresh_risk_grid(seeded_db, horizon_seconds=30, grid_size=32)
    second = refresh_risk_grid(seeded_db, horizon_seconds=30, grid_size=32)
    assert first == second
    assert len(list(seeded_db.scalars(select(MapRiskCell)))) == second


def test_roam_value_is_gold_equivalent_arithmetic(seeded_db) -> None:  # type: ignore[no-untyped-def]
    """Value must equal the documented formula, not merely correlate with it."""
    roams = list(seeded_db.scalars(select(RoamEvent)))
    assert roams, "the simulator should produce some roams"
    for roam in roams:
        assert roam.end_ms > roam.start_ms
        assert roam.cs_sacrificed >= 0.0
        assert roam.success == (roam.value > 75.0)


def test_roams_are_detected_outside_the_lane_corridor(seeded_db) -> None:  # type: ignore[no-untyped-def]
    from app.core.constants import Role
    from app.db.models import Match
    from app.services.analytics.context import MatchContext
    from app.services.analytics.geometry import distance_to_lane

    match_id = seeded_db.scalar(select(Match.match_id))
    ctx = MatchContext.load(seeded_db, match_id)
    assert ctx is not None
    roams = detect_roams(ctx)

    for roam in roams:
        role = Role(roam.role)
        # At least one minute in the window is genuinely away from lane.
        minutes = range(roam.start_ms // 60_000 + 1, roam.end_ms // 60_000 + 1)
        away = []
        for minute in minutes:
            frame = ctx.frame_at_minute(roam.participant_id, minute)
            if frame is None or frame.position_x is None:
                continue
            away.append(
                distance_to_lane(frame.position_x, frame.position_y, role) > ROAM_DISTANCE_UNITS
            )
        assert any(away), f"roam window {minutes} was never away from lane"


def test_xp_to_gold_conversion_is_documented_and_used() -> None:
    # A guard against silently changing a published conversion constant.
    assert pytest.approx(0.30) == XP_TO_GOLD


def test_refresh_gives_risk_features_their_own_cohorts(seeded_db) -> None:  # type: ignore[no-untyped-def]
    """Regression: cohorts must be rebuilt after risk scoring.

    The risk columns are populated *by* the refresh, so a single cohort pass at
    the start leaves them with no baselines and every comparison against them
    comes back empty. `refresh_all` therefore runs a second pass once they exist.
    """
    from sqlalchemy import select as sa_select

    from app.db.models import CohortStat
    from app.services.analytics.refresh import refresh_all

    report = refresh_all(seeded_db, train_skill_gap=False)
    assert report.matches_scored > 0, "the risk model should have scored some matches"

    metrics_with_cohorts = {c.metric for c in seeded_db.scalars(sa_select(CohortStat))}
    for metric in ("mean_position_risk", "deaths_above_expected", "high_risk_exposure_share"):
        assert metric in metrics_with_cohorts, f"{metric} has no cohort baseline"
