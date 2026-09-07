"""Static domain constants: routing, roles, ranks, and Summoner's Rift geometry.

Map coordinates come from the Match-V5 timeline `position` objects, which are
expressed in Summoner's Rift world units. The playable area spans roughly
(-120, -120) to (14870, 14980); we clamp to [0, 15000] for gridding.

The named-zone polylines below are approximations of lane centre-lines derived
from the map layout, not values published by Riot. They are used only to bucket
positions into human-readable regions, and every consumer treats the result as a
coarse label.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# --- Routing ------------------------------------------------------------------

#: platform host -> regional routing cluster used by account-v1 and match-v5
PLATFORM_TO_REGION: Final[dict[str, str]] = {
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "me1": "europe",
    "kr": "asia",
    "jp1": "asia",
    "tw2": "sea",
    "sg2": "sea",
    "vn2": "sea",
    "oc1": "sea",
    "ph2": "sea",
    "th2": "sea",
}

VALID_PLATFORMS: Final[frozenset[str]] = frozenset(PLATFORM_TO_REGION)


def region_for_platform(platform: str) -> str:
    """Map a platform host (``na1``) to its regional routing value (``americas``)."""
    try:
        return PLATFORM_TO_REGION[platform.lower()]
    except KeyError as exc:  # pragma: no cover - guarded at the API layer
        raise ValueError(f"unknown platform {platform!r}") from exc


# --- Roles & queues -----------------------------------------------------------


class Role(StrEnum):
    TOP = "TOP"
    JUNGLE = "JUNGLE"
    MIDDLE = "MIDDLE"
    BOTTOM = "BOTTOM"
    UTILITY = "UTILITY"
    UNKNOWN = "UNKNOWN"


LANE_ROLES: Final[frozenset[Role]] = frozenset({Role.TOP, Role.MIDDLE, Role.BOTTOM, Role.UTILITY})

QUEUE_NAMES: Final[dict[int, str]] = {
    400: "Normal Draft",
    420: "Ranked Solo/Duo",
    430: "Normal Blind",
    440: "Ranked Flex",
    450: "ARAM",
    700: "Clash",
}

#: Queues that use Summoner's Rift 5v5 and therefore support the full analytics suite.
SR_QUEUES: Final[frozenset[int]] = frozenset({400, 420, 430, 440, 700})


# --- Ranks --------------------------------------------------------------------

TIER_ORDER: Final[tuple[str, ...]] = (
    "IRON",
    "BRONZE",
    "SILVER",
    "GOLD",
    "PLATINUM",
    "EMERALD",
    "DIAMOND",
    "MASTER",
    "GRANDMASTER",
    "CHALLENGER",
)

DIVISION_ORDER: Final[tuple[str, ...]] = ("IV", "III", "II", "I")

#: Tiers that have no divisions.
APEX_TIERS: Final[frozenset[str]] = frozenset({"MASTER", "GRANDMASTER", "CHALLENGER"})


def tier_rank_score(tier: str | None, division: str | None = None, lp: int = 0) -> float:
    """Collapse tier/division/LP into a single monotone scalar.

    Below Master, one tier is worth 400 points, one division 100, and LP
    contributes its face value inside a division.

    Master, Grandmaster and Challenger share a single base and are separated by
    LP alone, because that is how the apex ladder actually works: they are not
    three tiers stacked on top of each other but one LP pool cut at two
    thresholds. Giving each its own 400-point base would rank a 2000 LP Master
    above a freshly promoted Challenger, which is backwards.

    Used as the ordinal target for rank-separation models and to order cohorts.
    """
    if not tier:
        return 0.0
    tier_up = tier.upper()
    if tier_up not in TIER_ORDER:
        return 0.0
    if tier_up in APEX_TIERS:
        return TIER_ORDER.index("MASTER") * 400.0 + max(0.0, min(float(lp), 3000.0))
    base = TIER_ORDER.index(tier_up) * 400.0
    div_idx = (
        DIVISION_ORDER.index(division.upper())
        if division and division.upper() in DIVISION_ORDER
        else 0
    )
    return base + div_idx * 100.0 + max(0.0, min(float(lp), 100.0))


def tier_group(tier: str | None) -> str:
    """Coarse cohort bucket used for peer comparison (keeps cohorts populated)."""
    if not tier:
        return "UNRANKED"
    t = tier.upper()
    if t in {"IRON", "BRONZE"}:
        return "IRON_BRONZE"
    if t in {"SILVER", "GOLD"}:
        return "SILVER_GOLD"
    if t in {"PLATINUM", "EMERALD"}:
        return "PLAT_EMERALD"
    if t == "DIAMOND":
        return "DIAMOND"
    if t in APEX_TIERS:
        return "MASTER_PLUS"
    return "UNRANKED"


TIER_GROUP_ORDER: Final[tuple[str, ...]] = (
    "IRON_BRONZE",
    "SILVER_GOLD",
    "PLAT_EMERALD",
    "DIAMOND",
    "MASTER_PLUS",
)


# --- Map geometry -------------------------------------------------------------

MAP_MIN: Final[float] = 0.0
MAP_MAX: Final[float] = 15000.0

#: Well-known objective pit centres (Summoner's Rift world units).
DRAGON_PIT: Final[tuple[float, float]] = (9866.0, 4414.0)
BARON_PIT: Final[tuple[float, float]] = (5007.0, 10471.0)
#: Rift Herald spawns in the Baron pit.
HERALD_PIT: Final[tuple[float, float]] = BARON_PIT

BLUE_BASE: Final[tuple[float, float]] = (1200.0, 1200.0)
RED_BASE: Final[tuple[float, float]] = (13800.0, 13800.0)

#: Lane centre-lines as polylines from the blue base to the red base.
LANE_POLYLINES: Final[dict[Role, tuple[tuple[float, float], ...]]] = {
    Role.TOP: (
        (1000.0, 4200.0),
        (1300.0, 10500.0),
        (2500.0, 12800.0),
        (5000.0, 13300.0),
        (11500.0, 13300.0),
        (13000.0, 12600.0),
    ),
    Role.MIDDLE: (
        (2200.0, 2200.0),
        (7000.0, 7000.0),
        (12800.0, 12800.0),
    ),
    Role.BOTTOM: (
        (4200.0, 1000.0),
        (10500.0, 1300.0),
        (12800.0, 2500.0),
        (13300.0, 5000.0),
        (13300.0, 11500.0),
        (12600.0, 13000.0),
    ),
}

#: Half-width (world units) of the "in lane" corridor around a lane centre-line.
LANE_HALF_WIDTH: Final[float] = 1500.0

#: The river is the anti-diagonal band where ``x + y`` is close to 15000.
RIVER_BAND: Final[float] = 1500.0

BASE_RADIUS: Final[float] = 3000.0
PIT_RADIUS: Final[float] = 1400.0


class Zone(StrEnum):
    """Human-readable map regions used by the spatial layer."""

    BLUE_BASE = "BLUE_BASE"
    RED_BASE = "RED_BASE"
    DRAGON_PIT = "DRAGON_PIT"
    BARON_PIT = "BARON_PIT"
    TOP_LANE = "TOP_LANE"
    MID_LANE = "MID_LANE"
    BOT_LANE = "BOT_LANE"
    TOP_RIVER = "TOP_RIVER"
    BOT_RIVER = "BOT_RIVER"
    BLUE_TOP_JUNGLE = "BLUE_TOP_JUNGLE"
    BLUE_BOT_JUNGLE = "BLUE_BOT_JUNGLE"
    RED_TOP_JUNGLE = "RED_TOP_JUNGLE"
    RED_BOT_JUNGLE = "RED_BOT_JUNGLE"


#: Zones a laner is expected to occupy; used by roam detection.
ROLE_HOME_ZONE: Final[dict[Role, Zone]] = {
    Role.TOP: Zone.TOP_LANE,
    Role.MIDDLE: Zone.MID_LANE,
    Role.BOTTOM: Zone.BOT_LANE,
    Role.UTILITY: Zone.BOT_LANE,
}


# --- Game phases --------------------------------------------------------------


class Phase(StrEnum):
    EARLY = "EARLY"  # 0-14 min: laning
    MID = "MID"  # 14-25 min: grouping / first objectives at scale
    LATE = "LATE"  # 25+ min


PHASE_BOUNDS_SECONDS: Final[tuple[int, int]] = (14 * 60, 25 * 60)


def phase_for_seconds(seconds: float) -> Phase:
    early, mid = PHASE_BOUNDS_SECONDS
    if seconds < early:
        return Phase.EARLY
    if seconds < mid:
        return Phase.MID
    return Phase.LATE


#: Duration cohort buckets (minutes) — game length materially changes every rate stat.
DURATION_BUCKETS: Final[tuple[tuple[str, float, float], ...]] = (
    ("SHORT", 0.0, 25.0),
    ("MEDIUM", 25.0, 32.0),
    ("LONG", 32.0, 1e9),
)


def duration_bucket(duration_seconds: float) -> str:
    minutes = duration_seconds / 60.0
    for name, lo, hi in DURATION_BUCKETS:
        if lo <= minutes < hi:
            return name
    return "LONG"


def parse_patch(game_version: str | None) -> str:
    """``14.19.624.1234`` -> ``14.19``. Unknown/blank input yields ``unknown``."""
    if not game_version:
        return "unknown"
    parts = game_version.split(".")
    if len(parts) < 2:
        return "unknown"
    return f"{parts[0]}.{parts[1]}"
