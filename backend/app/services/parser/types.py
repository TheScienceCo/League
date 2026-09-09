"""Types at the parser seam.

Everything downstream depends on these dataclasses and on the `ReplayParser`
Protocol — never on `mgz` directly. Swapping the parsing library, or stubbing it
in tests, means implementing this Protocol and nothing else.

**What a replay actually contains.** An `.aoe2record` is a command stream: the
inputs players sent to the engine, not the outcomes the engine produced. So
"player queued a villager at 4:32" is recorded; "a villager was created" is not,
because the queue may be cancelled or the building destroyed. Unit deaths, kills
and per-resource-type stockpiles are *absent from the command stream entirely*.
`Availability` below exists so that consumers can distinguish "zero" from
"we cannot know", and so the UI never renders an invented number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Availability(str, Enum):
    """How a given quantity was arrived at."""

    #: Read directly out of the command stream. Exact.
    OBSERVED = "observed"
    #: Derived from observed commands under stated assumptions.
    RECONSTRUCTED = "reconstructed"
    #: Read from DE sync packets, whose field meanings are community-reverse-
    #: engineered rather than documented. Directionally right, not exact.
    INFERRED = "inferred"
    #: Not recoverable from a replay file. Never render a number for these.
    UNAVAILABLE = "unavailable"


class CommandType(str, Enum):
    """Normalised command types we retain. Anything else is dropped."""

    QUEUE_UNIT = "queue_unit"
    BUILD = "build"
    RESEARCH = "research"
    AGE_UP = "age_up"
    TRIBUTE = "tribute"
    DELETE = "delete"
    MARKET_BUY = "market_buy"
    MARKET_SELL = "market_sell"
    TOWN_BELL = "town_bell"
    BACK_TO_WORK = "back_to_work"
    RESIGN = "resign"


@dataclass(frozen=True)
class Command:
    """One timestamped player command."""

    timestamp_ms: int
    player_number: int
    type: CommandType
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceSample:
    """A point on the banked-resource curve, from a DE sync packet.

    `total_resources` is the sum of food+wood+gold+stone: the per-type split is
    not present. Treat as `Availability.INFERRED`.
    """

    timestamp_ms: int
    player_number: int
    total_resources: int
    object_count: int


@dataclass
class ParsedPlayer:
    player_number: int
    name: str
    civilization: str
    team: int | None = None
    winner: bool | None = None
    rating: int | None = None
    profile_id: int | None = None
    color_id: int | None = None
    #: Effective APM as computed by mgz (excludes spam/duplicate orders).
    eapm: int | None = None


@dataclass
class ParsedReplay:
    """The full result of parsing one replay file."""

    map_name: str | None
    map_size: str | None
    duration_ms: int
    version: str | None
    played_at: str | None
    players: list[ParsedPlayer]
    commands: list[Command]
    resource_samples: list[ResourceSample]
    postgame: dict[str, Any] | None = None
    #: Non-fatal problems encountered while parsing (truncated body, unknown
    #: actions). The analysis still runs; the report surfaces these.
    warnings: list[str] = field(default_factory=list)

    def commands_for(self, player_number: int) -> list[Command]:
        return [c for c in self.commands if c.player_number == player_number]

    def samples_for(self, player_number: int) -> list[ResourceSample]:
        return [s for s in self.resource_samples if s.player_number == player_number]


class ReplayParseError(Exception):
    """Raised when a file cannot be parsed as a replay at all."""


class ReplayParser(Protocol):
    """The seam. Implement this to swap parsing backends."""

    name: str

    def parse(self, data: bytes) -> ParsedReplay: ...
