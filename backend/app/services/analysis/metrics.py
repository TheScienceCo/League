"""Derive metrics from a parsed replay.

Every number this module produces carries an `Availability` saying how it was
obtained, because a replay is a *command stream* and large parts of the game are
simply not in it. Combat outcomes are the clearest example: no replay records a
unit death, so kill/loss ratios cannot be computed and are reported as
`UNAVAILABLE` rather than as zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from statistics import mean

from app.services.parser.types import (
    Availability,
    CommandType,
    ParsedReplay,
)

#: Banked resources above which a player is meaningfully floating. 1000 is about
#: the cost of a Town Center plus change: enough that it should have been spent.
FLOAT_THRESHOLD = 1000

#: Buildings whose first appearance identifies an opening.
_OPENING_MARKERS = {
    "Archery Range": "archers",
    "Stable": "scouts",
    "Barracks": "militia line",
    "Watch Tower": "tower rush",
}

_AGE_ORDER = ["dark", "feudal", "castle", "imperial"]


@dataclass
class Metric:
    """One derived number, with provenance."""

    key: str
    label: str
    value: float | int | None
    unit: str
    availability: Availability
    note: str | None = None

    @property
    def is_known(self) -> bool:
        return self.value is not None and self.availability is not Availability.UNAVAILABLE


@dataclass
class PlayerAnalysis:
    player_number: int
    name: str
    civilization: str
    winner: bool | None
    metrics: dict[str, Metric] = field(default_factory=dict)
    age_timings_ms: dict[str, int] = field(default_factory=dict)
    build_order: list[dict] = field(default_factory=list)
    resource_curve: list[dict] = field(default_factory=list)
    #: Mean banked resources within each age reached, e.g. {"dark": 180, "feudal": 640}.
    float_by_age: dict[str, int] = field(default_factory=dict)
    opening: str | None = None
    #: When the building that identified the opening was placed, in ms.
    opening_evidence_ms: int | None = None


@dataclass
class MatchAnalysis:
    map_name: str | None
    duration_ms: int
    version: str | None
    players: list[PlayerAnalysis]
    warnings: list[str] = field(default_factory=list)


def analyze(replay: ParsedReplay) -> MatchAnalysis:
    """Turn a parsed replay into per-player metrics."""
    analyses = [_analyze_player(replay, p.player_number) for p in replay.players]
    _add_opponent_differentials(analyses)
    return MatchAnalysis(
        map_name=replay.map_name,
        duration_ms=replay.duration_ms,
        version=replay.version,
        players=analyses,
        warnings=list(replay.warnings),
    )


def _analyze_player(replay: ParsedReplay, number: int) -> PlayerAnalysis:
    player = next(p for p in replay.players if p.player_number == number)
    commands = replay.commands_for(number)
    samples = replay.samples_for(number)

    ages = {
        c.payload["age"]: c.timestamp_ms
        for c in commands
        if c.type is CommandType.AGE_UP and c.payload.get("age")
    }
    builds = [c for c in commands if c.type is CommandType.BUILD]
    researches = [c for c in commands if c.type is CommandType.RESEARCH]
    queues = [c for c in commands if c.type is CommandType.QUEUE_UNIT]

    analysis = PlayerAnalysis(
        player_number=number,
        name=player.name,
        civilization=player.civilization,
        winner=player.winner,
        age_timings_ms=ages,
        build_order=[
            {
                "timestamp_ms": c.timestamp_ms,
                "building": c.payload.get("building") or f"unknown_{c.payload.get('building_id')}",
                "x": c.payload.get("x"),
                "y": c.payload.get("y"),
            }
            for c in builds[:40]
        ],
        resource_curve=[
            {"timestamp_ms": s.timestamp_ms, "banked": s.total_resources, "objects": s.object_count}
            for s in samples
        ],
    )
    analysis.opening, analysis.opening_evidence_ms = _classify_opening(builds, ages)

    m = analysis.metrics

    # --- Age timings: the most reliable signal in a replay -----------------
    for age in ("feudal", "castle", "imperial"):
        m[f"{age}_time"] = Metric(
            key=f"{age}_time",
            label=f"{age.title()} Age reached",
            value=ages.get(age),
            unit="ms",
            availability=Availability.OBSERVED
            if age in ages
            else Availability.UNAVAILABLE,
            note=None if age in ages else "Player did not reach this age.",
        )

    # --- Banked resources, from DE sync packets ---------------------------
    if samples:
        banked = [s.total_resources for s in samples]
        m["float_mean"] = Metric(
            "float_mean", "Average banked resources", round(mean(banked)), "resources",
            Availability.INFERRED,
            "Sum of all four resources. Sync-packet field meanings are "
            "community-reverse-engineered, so treat as approximate.",
        )
        m["float_peak"] = Metric(
            "float_peak", "Peak banked resources", max(banked), "resources",
            Availability.INFERRED,
        )
        over = _time_above(samples, FLOAT_THRESHOLD)
        m["time_floating"] = Metric(
            "time_floating", f"Time above {FLOAT_THRESHOLD} banked", over, "ms",
            Availability.INFERRED,
            "Resources sitting in the bank are resources not converted into "
            "army, economy or upgrades.",
        )
        analysis.float_by_age = _float_by_age(samples, ages, replay.duration_ms)
    else:
        for k, lbl in (
            ("float_mean", "Average banked resources"),
            ("float_peak", "Peak banked resources"),
            ("time_floating", f"Time above {FLOAT_THRESHOLD} banked"),
        ):
            m[k] = Metric(k, lbl, None, "resources", Availability.UNAVAILABLE,
                          "No sync telemetry in this replay version.")

    # --- Build order ------------------------------------------------------
    m["buildings_placed"] = Metric(
        "buildings_placed", "Buildings placed", len(builds), "count", Availability.OBSERVED,
        "Build commands issued. A placed foundation may be cancelled or "
        "destroyed before completing.",
    )
    m["technologies_researched"] = Metric(
        "technologies_researched", "Technologies researched", len(researches), "count",
        Availability.OBSERVED,
    )
    m["eapm"] = Metric(
        "eapm", "Effective APM", player.eapm, "apm",
        Availability.OBSERVED if player.eapm is not None else Availability.UNAVAILABLE,
    )

    # --- Production: only when the replay version exposes queue commands ---
    if queues:
        villager_queues = [c for c in queues if c.payload.get("unit") == "Villager"]
        m["villagers_queued"] = Metric(
            "villagers_queued", "Villagers queued",
            sum(int(c.payload.get("amount") or 1) for c in villager_queues),
            "count", Availability.OBSERVED,
            "Queue commands, not completed villagers: a queue can be cancelled.",
        )
        m["max_production_gap"] = Metric(
            "max_production_gap", "Longest gap between villager queues",
            _max_gap(villager_queues, replay.duration_ms), "ms",
            Availability.RECONSTRUCTED,
            "A proxy for Town Center idle time. It cannot distinguish an idle "
            "TC from a full queue still producing.",
        )
    else:
        for k, lbl in (
            ("villagers_queued", "Villagers queued"),
            ("max_production_gap", "Longest gap between villager queues"),
        ):
            m[k] = Metric(k, lbl, None, "count", Availability.UNAVAILABLE,
                          "Unit-queue commands are not decodable for this replay version.")

    # --- Genuinely absent from every replay -------------------------------
    for k, lbl in (
        ("resources_killed", "Resources destroyed in combat"),
        ("resources_lost", "Resources lost in combat"),
        ("engagement_efficiency", "Engagement efficiency"),
    ):
        m[k] = Metric(k, lbl, None, "resources", Availability.UNAVAILABLE,
                      "Replays record commands, not outcomes. Unit deaths and "
                      "combat results are not present in the file.")

    return analysis


def _time_above(samples, threshold: int) -> int:
    """Milliseconds spent above `threshold` banked, by trapezoid over samples."""
    total = 0
    for prev, cur in pairwise(samples):
        if prev.total_resources > threshold:
            total += cur.timestamp_ms - prev.timestamp_ms
    return total


def _float_by_age(samples, ages: dict[str, int], duration_ms: int) -> dict[str, int]:
    """Mean banked resources within each age the player reached."""
    bounds: list[tuple[str, int, int]] = []
    starts = [("dark", 0)] + [(a, ages[a]) for a in _AGE_ORDER[1:] if a in ages]
    for i, (name, start) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else duration_ms
        bounds.append((name, start, end))
    out: dict[str, int] = {}
    for name, start, end in bounds:
        vals = [s.total_resources for s in samples if start <= s.timestamp_ms < end]
        if vals:
            out[name] = round(mean(vals))
    return out


def _max_gap(queue_commands, duration_ms: int) -> int | None:
    if not queue_commands:
        return None
    times = [c.timestamp_ms for c in queue_commands]
    gaps = [b - a for a, b in pairwise(times)]
    return max(gaps) if gaps else None


def _classify_opening(builds, ages: dict[str, int]) -> tuple[str, int | None]:
    """Name the opening from the first military building placed before Castle.

    Deliberately conservative: when the marker buildings are absent or the build
    data is thin, this returns "unclassified" rather than guessing.
    """
    castle_ms = ages.get("castle")
    pre_castle = [b for b in builds if castle_ms is None or b.timestamp_ms < castle_ms]
    for b in pre_castle:
        name = b.payload.get("building")
        if name in _OPENING_MARKERS:
            return _OPENING_MARKERS[name], b.timestamp_ms
    if castle_ms is not None:
        return "fast castle", castle_ms
    return "unclassified", None


def _add_opponent_differentials(analyses: list[PlayerAnalysis]) -> None:
    """Age timings relative to the fastest other player.

    In a 1v1 this is the head-to-head gap; in a team game it is the gap to the
    fastest opponent, which is the number that actually constrains you.
    """
    for a in analyses:
        others = [o for o in analyses if o.player_number != a.player_number]
        for age in ("feudal", "castle", "imperial"):
            mine = a.age_timings_ms.get(age)
            theirs = [o.age_timings_ms[age] for o in others if age in o.age_timings_ms]
            key = f"{age}_delta"
            if mine is None or not theirs:
                a.metrics[key] = Metric(
                    key, f"{age.title()} Age vs opponent", None, "ms",
                    Availability.UNAVAILABLE,
                    "Requires both players to have reached this age.",
                )
            else:
                a.metrics[key] = Metric(
                    key, f"{age.title()} Age vs opponent", mine - min(theirs), "ms",
                    Availability.OBSERVED,
                    "Negative is faster than the opponent.",
                )
