"""Lookups against the AoE2 reference dataset shipped with `aocref`.

Object and technology IDs are resolved to names through the dataset rather than
hard-coded here, because a single logical entity has many IDs: a Town Center is
71, 109, 141, 142, 481-484, 597 and 611-621 depending on civilisation, age and
graphic variant. Grouping by resolved *name* is the only stable way to ask
"is this a Town Center?".
"""

from __future__ import annotations

from functools import lru_cache

from mgz.reference import get_dataset
from mgz.util import Version

#: Technology IDs for age advancement. These three are stable across every
#: dataset and are the anchor for all build-order timing.
AGE_TECHNOLOGIES: dict[int, str] = {101: "feudal", 102: "castle", 103: "imperial"}

#: Buildings that produce military units. Used for production-uptime metrics.
MILITARY_PRODUCTION_BUILDINGS = frozenset(
    {"Barracks", "Archery Range", "Stable", "Siege Workshop", "Castle", "Dock"}
)

#: Buildings that mark an economic expansion rather than military capacity.
ECONOMIC_BUILDINGS = frozenset(
    {"Town Center", "Mill", "Lumber Camp", "Mining Camp", "Farm", "House"}
)


@lru_cache(maxsize=4)
def _dataset(dataset_id: int = 100) -> dict:
    _, data = get_dataset(Version.DE, None)
    return data


@lru_cache(maxsize=1)
def _objects() -> dict[int, str]:
    raw = _dataset().get("objects", {})
    return {int(k): _name_of(v) for k, v in raw.items()}


@lru_cache(maxsize=1)
def _technologies() -> dict[int, str]:
    raw = _dataset().get("technologies", {})
    return {int(k): _name_of(v) for k, v in raw.items()}


def _name_of(entry: object) -> str:
    if isinstance(entry, dict):
        return str(entry.get("name") or "")
    return str(entry or "")


def object_name(object_id: int) -> str | None:
    """Resolve an object (unit or building) ID to its display name."""
    name = _objects().get(object_id)
    return name or None


def technology_name(technology_id: int) -> str | None:
    """Resolve a technology ID to its display name."""
    name = _technologies().get(technology_id)
    return name or None


def is_villager(object_id: int) -> bool:
    return object_name(object_id) == "Villager"


def is_town_center(object_id: int) -> bool:
    return object_name(object_id) == "Town Center"


def is_military_production_building(object_id: int) -> bool:
    return object_name(object_id) in MILITARY_PRODUCTION_BUILDINGS


def age_from_technology(technology_id: int) -> str | None:
    """Return "feudal"/"castle"/"imperial" if this tech is an age advance."""
    return AGE_TECHNOLOGIES.get(technology_id)
