"""Summoner's Rift geometry helpers.

Everything spatial in the project funnels through here: zone labelling, lane
distance, gridding for the heatmap, and the lane-progress parameterisation used
to describe where along a lane a position sits.
"""

from __future__ import annotations

import math
from functools import lru_cache

from app.core.constants import (
    BARON_PIT,
    BASE_RADIUS,
    BLUE_BASE,
    DRAGON_PIT,
    LANE_HALF_WIDTH,
    LANE_POLYLINES,
    MAP_MAX,
    MAP_MIN,
    PIT_RADIUS,
    RED_BASE,
    RIVER_BAND,
    Role,
    Zone,
)

Point = tuple[float, float]


def clamp(x: float, y: float) -> Point:
    return (
        min(max(x, MAP_MIN), MAP_MAX),
        min(max(y, MAP_MIN), MAP_MAX),
    )


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    """Shortest distance from point `p` to segment `ab`."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


@lru_cache(maxsize=8)
def _polyline_lengths(role: Role) -> tuple[tuple[float, ...], float]:
    """Cumulative segment lengths for a lane, plus total length."""
    pts = LANE_POLYLINES[role]
    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + distance(pts[i - 1], pts[i]))
    return tuple(cum), cum[-1]


def lane_point(role: Role, progress: float) -> Point:
    """Point at `progress` (0 = blue base end, 1 = red base end) along a lane."""
    lane = Role.BOTTOM if role is Role.UTILITY else role
    if lane not in LANE_POLYLINES:
        lane = Role.MIDDLE
    pts = LANE_POLYLINES[lane]
    cum, total = _polyline_lengths(lane)
    target = max(0.0, min(1.0, progress)) * total
    for i in range(1, len(pts)):
        if target <= cum[i] or i == len(pts) - 1:
            seg_len = cum[i] - cum[i - 1]
            t = 0.0 if seg_len == 0 else (target - cum[i - 1]) / seg_len
            ax, ay = pts[i - 1]
            bx, by = pts[i]
            return (ax + t * (bx - ax), ay + t * (by - ay))
    return pts[-1]


def distance_to_lane(x: float, y: float, role: Role) -> float:
    """Perpendicular distance from a position to a lane centre-line."""
    lane = Role.BOTTOM if role is Role.UTILITY else role
    if lane not in LANE_POLYLINES:
        return float("inf")
    pts = LANE_POLYLINES[lane]
    return min(point_segment_distance((x, y), pts[i - 1], pts[i]) for i in range(1, len(pts)))


def nearest_lane(x: float, y: float) -> tuple[Role, float]:
    """The closest lane and the distance to it."""
    best: tuple[Role, float] = (Role.MIDDLE, float("inf"))
    for role in (Role.TOP, Role.MIDDLE, Role.BOTTOM):
        d = distance_to_lane(x, y, role)
        if d < best[1]:
            best = (role, d)
    return best


def _is_river(x: float, y: float) -> bool:
    """The river is the anti-diagonal band through the middle of the map."""
    return abs((x + y) - 15000.0) < RIVER_BAND


def classify_zone(x: float, y: float) -> Zone:
    """Bucket a world position into a named region.

    Priority is deliberate: pits and bases win over lanes, lanes win over river,
    and anything left over is jungle. Mid lane and river overlap geometrically,
    so mid is only claimed when the position is genuinely close to the lane.
    """
    x, y = clamp(x, y)
    p = (x, y)

    if distance(p, DRAGON_PIT) < PIT_RADIUS:
        return Zone.DRAGON_PIT
    if distance(p, BARON_PIT) < PIT_RADIUS:
        return Zone.BARON_PIT
    if distance(p, BLUE_BASE) < BASE_RADIUS:
        return Zone.BLUE_BASE
    if distance(p, RED_BASE) < BASE_RADIUS:
        return Zone.RED_BASE

    d_top = distance_to_lane(x, y, Role.TOP)
    d_mid = distance_to_lane(x, y, Role.MIDDLE)
    d_bot = distance_to_lane(x, y, Role.BOTTOM)
    nearest = min(d_top, d_mid, d_bot)
    if nearest < LANE_HALF_WIDTH:
        if nearest == d_top:
            return Zone.TOP_LANE
        if nearest == d_bot:
            return Zone.BOT_LANE
        return Zone.MID_LANE

    if _is_river(x, y):
        # Above the mid diagonal (y > x) is the Baron/top half of the river.
        return Zone.TOP_RIVER if y > x else Zone.BOT_RIVER

    blue_half = (x + y) < 15000.0
    top_half = y > x
    if blue_half:
        return Zone.BLUE_TOP_JUNGLE if top_half else Zone.BLUE_BOT_JUNGLE
    return Zone.RED_TOP_JUNGLE if top_half else Zone.RED_BOT_JUNGLE


def grid_cell(x: float, y: float, grid_size: int) -> tuple[int, int]:
    """Map a position to a `grid_size` x `grid_size` cell index."""
    x, y = clamp(x, y)
    span = (MAP_MAX - MAP_MIN) / grid_size
    cx = min(int((x - MAP_MIN) / span), grid_size - 1)
    cy = min(int((y - MAP_MIN) / span), grid_size - 1)
    return cx, cy


def cell_center(cx: int, cy: int, grid_size: int) -> Point:
    span = (MAP_MAX - MAP_MIN) / grid_size
    return (MAP_MIN + (cx + 0.5) * span, MAP_MIN + (cy + 0.5) * span)


def is_enemy_half(x: float, y: float, team_id: int) -> bool:
    """True when the position is on the opposing team's side of the river.

    Team 100 spawns bottom-left, team 200 top-right.
    """
    blue_half = (x + y) < 15000.0
    return not blue_half if team_id == 100 else blue_half
