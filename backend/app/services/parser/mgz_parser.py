"""Replay parsing backed by `mgz` (aoc-mgz).

This is the only module in the codebase that imports `mgz`. Everything else
depends on `app.services.parser.types`.

**Parse-quality caveat.** `mgz` decodes actions per replay version, and unit
queue commands in particular are not decodable on every version: on some builds
they arrive as `Action.ERROR`. Rather than silently reporting "0 villagers
queued" for such a file, the parser records whether queue data was recoverable
and the analysis marks the dependent metrics `UNAVAILABLE`.
"""

from __future__ import annotations

import io
from datetime import timedelta
from typing import Any

from app.core.logging import get_logger
from app.services.parser.reference import age_from_technology, technology_name
from app.services.parser.types import (
    Command,
    CommandType,
    ParsedPlayer,
    ParsedReplay,
    ReplayParseError,
    ResourceSample,
)

log = get_logger(__name__)

#: Raw action names that represent queuing a unit at a production building.
_QUEUE_ACTIONS = {"QUEUE", "MULTIQUEUE", "DE_QUEUE"}

#: Above this share of undecodable actions the command stream is too damaged to
#: draw build-order conclusions from, and the report says so.
_ERROR_RATIO_UNRELIABLE = 0.25


def _ms(delta: timedelta | None) -> int:
    return int(delta.total_seconds() * 1000) if delta is not None else 0


class MgzReplayParser:
    """Parses `.aoe2record` / `.mgz` files via `mgz.model.parse_match`."""

    name = "mgz"

    def parse(self, data: bytes) -> ParsedReplay:
        if not data:
            raise ReplayParseError("empty file")

        try:
            from mgz.model import parse_match
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise ReplayParseError(f"mgz is not installed: {exc}") from exc

        try:
            match = parse_match(io.BytesIO(data))
        except Exception as exc:
            # mgz raises a wide range of types (struct.error, RuntimeError,
            # EOFError, zlib.error) for a malformed or unsupported file. The
            # caller only needs to know it was not parseable.
            raise ReplayParseError(f"{type(exc).__name__}: {exc}") from exc

        warnings: list[str] = []
        players = self._players(match)
        commands, queue_seen, error_ratio = self._commands(match, warnings)
        samples = self._samples(match)
        age_commands = self._age_commands(match)

        if error_ratio > _ERROR_RATIO_UNRELIABLE:
            warnings.append(
                f"{error_ratio:.0%} of actions could not be decoded for this replay "
                f"version; build-order detail is incomplete."
            )
        if not queue_seen:
            warnings.append(
                "Unit-queue commands are not decodable for this replay version, so "
                "production metrics (villager uptime, TC idle time) are unavailable."
            )

        return ParsedReplay(
            map_name=getattr(match.map, "name", None),
            map_size=getattr(match.map, "size", None),
            duration_ms=_ms(match.duration),
            version=str(getattr(match, "game_version", "") or "") or None,
            played_at=(ts.isoformat() if (ts := getattr(match, "timestamp", None)) else None),
            players=players,
            commands=sorted(commands + age_commands, key=lambda c: c.timestamp_ms),
            resource_samples=samples,
            postgame=self._postgame(match),
            warnings=warnings,
        )

    # -- pieces ------------------------------------------------------------

    def _players(self, match: Any) -> list[ParsedPlayer]:
        out: list[ParsedPlayer] = []
        for p in match.players:
            out.append(
                ParsedPlayer(
                    player_number=p.number,
                    name=p.name,
                    civilization=str(p.civilization),
                    team=getattr(p, "team_id", None),
                    winner=bool(getattr(p, "winner", False)),
                    rating=getattr(p, "rate_snapshot", None),
                    profile_id=getattr(p, "profile_id", None),
                    color_id=getattr(p, "color_id", None),
                    eapm=getattr(p, "eapm", None),
                )
            )
        return out

    def _age_commands(self, match: Any) -> list[Command]:
        """Age advances, from the model's `uptimes`.

        These are the single most reliable timing signal in a replay: mgz
        derives them from the game's own age transitions rather than from a
        command we have to decode.
        """
        out: list[Command] = []
        for up in getattr(match, "uptimes", []) or []:
            player = getattr(up, "player", None)
            if player is None:
                continue
            age = getattr(up.age, "name", "").replace("_AGE", "").lower()
            if not age:
                continue
            out.append(
                Command(
                    timestamp_ms=_ms(up.timestamp),
                    player_number=player.number,
                    type=CommandType.AGE_UP,
                    payload={"age": age},
                )
            )
        return out

    def _commands(
        self, match: Any, warnings: list[str]
    ) -> tuple[list[Command], bool, float]:
        out: list[Command] = []
        queue_seen = False
        total = 0
        errors = 0

        for action in getattr(match, "actions", []) or []:
            total += 1
            type_name = getattr(action.type, "name", "")
            if type_name == "ERROR":
                errors += 1
                continue

            player = getattr(action, "player", None)
            if player is None:
                continue
            payload = action.payload or {}
            ts = _ms(action.timestamp)

            command = self._to_command(type_name, ts, player.number, payload)
            if command is None:
                continue
            if command.type is CommandType.QUEUE_UNIT:
                queue_seen = True
            out.append(command)

        return out, queue_seen, (errors / total if total else 0.0)

    def _to_command(
        self, type_name: str, ts: int, player_number: int, payload: dict
    ) -> Command | None:
        """Map one raw mgz action onto our normalised command vocabulary.

        Unrecognised actions are dropped rather than guessed at.
        """
        if type_name == "BUILD":
            from app.services.parser.reference import object_name

            building_id = payload.get("building_id")
            return Command(
                ts,
                player_number,
                CommandType.BUILD,
                {
                    "building_id": building_id,
                    "building": object_name(building_id) if building_id else None,
                    "x": payload.get("x"),
                    "y": payload.get("y"),
                },
            )

        if type_name == "RESEARCH":
            tech_id = payload.get("technology_id")
            if tech_id is None:
                return None
            # An age advance is a research command, but we take age timings from
            # `uptimes` instead, which is more reliable. Drop the duplicate.
            if age_from_technology(tech_id) is not None:
                return None
            return Command(
                ts,
                player_number,
                CommandType.RESEARCH,
                {"technology_id": tech_id, "technology": technology_name(tech_id)},
            )

        if type_name in _QUEUE_ACTIONS:
            from app.services.parser.reference import object_name

            unit_id = payload.get("unit_id")
            return Command(
                ts,
                player_number,
                CommandType.QUEUE_UNIT,
                {
                    "unit_id": unit_id,
                    "unit": object_name(unit_id) if unit_id else None,
                    "amount": payload.get("amount", 1),
                    "building_object_ids": list(payload.get("object_ids") or []),
                },
            )

        if type_name in ("TRIBUTE", "DE_TRIBUTE"):
            return Command(
                ts,
                player_number,
                CommandType.TRIBUTE,
                {
                    k: payload.get(k)
                    for k in ("player_id_to", "food", "wood", "gold", "stone", "amount")
                },
            )

        if type_name == "DELETE":
            return Command(ts, player_number, CommandType.DELETE, {})
        if type_name == "BUY":
            return Command(ts, player_number, CommandType.MARKET_BUY, dict(payload))
        if type_name == "SELL":
            return Command(ts, player_number, CommandType.MARKET_SELL, dict(payload))
        if type_name == "TOWN_BELL":
            return Command(ts, player_number, CommandType.TOWN_BELL, {})
        if type_name == "BACK_TO_WORK":
            return Command(ts, player_number, CommandType.BACK_TO_WORK, {})
        if type_name == "RESIGN":
            return Command(ts, player_number, CommandType.RESIGN, {})
        return None

    def _samples(self, match: Any) -> list[ResourceSample]:
        """The banked-resource curve, from DE sync packets.

        `total_resources` is food+wood+gold+stone combined; the per-type split is
        not transmitted. Marked `INFERRED` downstream because the field meanings
        are community-reverse-engineered rather than documented.
        """
        out: list[ResourceSample] = []
        for p in match.players:
            for row in getattr(p, "timeseries", []) or []:
                out.append(
                    ResourceSample(
                        timestamp_ms=_ms(row.timestamp),
                        player_number=p.number,
                        total_resources=int(row.total_resources),
                        object_count=int(row.total_objects),
                    )
                )
        out.sort(key=lambda s: (s.timestamp_ms, s.player_number))
        return out

    def _postgame(self, match: Any) -> dict[str, Any] | None:
        pg = getattr(match, "postgame", None)
        return dict(pg) if isinstance(pg, dict) else None
