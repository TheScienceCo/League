"""Map geometry: zone classification, lane distance, gridding."""

from __future__ import annotations

import pytest

from app.core.constants import BARON_PIT, DRAGON_PIT, Role, Zone
from app.services.analytics.geometry import (
    cell_center,
    clamp,
    classify_zone,
    distance_to_lane,
    grid_cell,
    is_enemy_half,
    lane_point,
    nearest_lane,
    point_segment_distance,
)


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        (DRAGON_PIT, Zone.DRAGON_PIT),
        (BARON_PIT, Zone.BARON_PIT),
        ((1000.0, 1000.0), Zone.BLUE_BASE),
        ((14000.0, 14000.0), Zone.RED_BASE),
        ((7500.0, 7500.0), Zone.MID_LANE),
        ((1200.0, 8000.0), Zone.TOP_LANE),
        ((8000.0, 1200.0), Zone.BOT_LANE),
        ((6500.0, 9000.0), Zone.TOP_RIVER),
        ((9000.0, 6500.0), Zone.BOT_RIVER),
        ((4000.0, 9000.0), Zone.BLUE_TOP_JUNGLE),
        ((11000.0, 6500.0), Zone.RED_BOT_JUNGLE),
    ],
)
def test_zone_classification(point: tuple[float, float], expected: Zone) -> None:
    assert classify_zone(*point) is expected


def test_clamp_keeps_positions_on_the_map() -> None:
    assert clamp(-500.0, 99999.0) == (0.0, 15000.0)


def test_lane_point_runs_from_blue_to_red() -> None:
    start = lane_point(Role.MIDDLE, 0.0)
    end = lane_point(Role.MIDDLE, 1.0)
    assert start[0] < end[0] and start[1] < end[1]
    # Mid lane is the diagonal, so its midpoint sits near the map centre.
    mid = lane_point(Role.MIDDLE, 0.5)
    assert abs(mid[0] - mid[1]) < 100


def test_support_shares_the_bottom_lane() -> None:
    assert lane_point(Role.UTILITY, 0.4) == lane_point(Role.BOTTOM, 0.4)
    x, y = lane_point(Role.BOTTOM, 0.5)
    assert distance_to_lane(x, y, Role.UTILITY) < 1.0


def test_distance_to_lane_is_zero_on_the_centre_line() -> None:
    for role in (Role.TOP, Role.MIDDLE, Role.BOTTOM):
        x, y = lane_point(role, 0.35)
        assert distance_to_lane(x, y, role) < 1.0


def test_nearest_lane_finds_the_right_lane() -> None:
    x, y = lane_point(Role.TOP, 0.5)
    role, distance = nearest_lane(x, y)
    assert role is Role.TOP
    assert distance < 1.0


def test_point_segment_distance_handles_degenerate_segment() -> None:
    assert point_segment_distance((3.0, 4.0), (0.0, 0.0), (0.0, 0.0)) == pytest.approx(5.0)


def test_grid_cell_round_trips_through_its_centre() -> None:
    for x, y in [(0.0, 0.0), (7500.0, 7500.0), (14999.0, 14999.0)]:
        cx, cy = grid_cell(x, y, 32)
        assert 0 <= cx < 32 and 0 <= cy < 32
        assert grid_cell(*cell_center(cx, cy, 32), 32) == (cx, cy)


def test_enemy_half_is_symmetric_between_teams() -> None:
    # Deep in the red-side jungle.
    assert is_enemy_half(12000.0, 9000.0, team_id=100) is True
    assert is_enemy_half(12000.0, 9000.0, team_id=200) is False
