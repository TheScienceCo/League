"""AoE2 replay parser integration and event extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class ReplayMetadata:
    """Extracted metadata from a replay file."""

    map_name: str | None = None
    map_type: str | None = None
    duration_seconds: int = 0
    player_count: int = 0
    patch_version: str | None = None
    game_version: str | None = None
    players: list[dict[str, Any]] | None = None


@dataclass
class ParsedReplay:
    """Result of parsing a replay file."""

    metadata: ReplayMetadata
    events: list[dict[str, Any]]
    players: list[dict[str, Any]]
    success: bool
    error: str | None = None


class ReplayParser:
    """
    Replay parser adapter.

    This is an abstraction layer over the actual replay parsing library
    (aoc-mgz, mgz, etc.). This allows switching implementations.

    For MVP, this provides a deterministic mock parser that generates
    realistic test data.
    """

    def __init__(self, parser_type: str = "aoc_mgz"):
        """
        Initialize parser.

        Args:
            parser_type: Type of parser ("aoc_mgz", "mgz", or "mock")
        """
        self.parser_type = parser_type
        log.info("Initialized replay parser", parser_type=parser_type)

    async def parse(self, file_path: str) -> ParsedReplay:
        """
        Parse a replay file.

        Args:
            file_path: Path to the .aoe2record file

        Returns:
            ParsedReplay with metadata and event stream
        """
        try:
            if self.parser_type == "mock":
                return self._parse_mock(file_path)
            else:
                return await self._parse_real(file_path)
        except Exception as e:
            log.error("Replay parsing failed", file_path=file_path, error=str(e))
            return ParsedReplay(
                metadata=ReplayMetadata(),
                events=[],
                players=[],
                success=False,
                error=str(e),
            )

    async def _parse_real(self, file_path: str) -> ParsedReplay:
        """Parse using actual aoc-mgz or similar library."""
        # TODO: Implement actual parsing when aoc-mgz is installed
        # For now, return mock
        log.warning("Real parser not yet implemented, using mock", file_path=file_path)
        return self._parse_mock(file_path)

    def _parse_mock(self, file_path: str) -> ParsedReplay:
        """
        Return deterministic mock replay data for testing.

        This demonstrates the expected output structure.
        """
        metadata = ReplayMetadata(
            map_name="Arabia",
            map_type="arabia",
            duration_seconds=1847,
            player_count=2,
            patch_version="101.101",
            game_version="1.0",
            players=[
                {
                    "player_id": 1,
                    "name": "MockPlayer1",
                    "civilization": "britons",
                    "team": 1,
                    "starting_position": 1,
                    "result": "win",
                },
                {
                    "player_id": 2,
                    "name": "MockPlayer2",
                    "civilization": "franks",
                    "team": 2,
                    "starting_position": 2,
                    "result": "loss",
                },
            ],
        )

        # Generate deterministic but realistic events
        events = self._generate_mock_events(1847)

        return ParsedReplay(
            metadata=metadata,
            events=events,
            players=metadata.players or [],
            success=True,
        )

    def _generate_mock_events(self, duration_seconds: int) -> list[dict[str, Any]]:
        """Generate mock event stream for testing."""
        events = []

        # Age advances (typical timings)
        events.append(
            {
                "type": "age_up",
                "timestamp_ms": 10 * 60 * 1000,  # 10:00
                "player_id": 1,
                "age": 2,
                "data": {},
            }
        )
        events.append(
            {
                "type": "age_up",
                "timestamp_ms": 10 * 60 * 1000 + 500,
                "player_id": 2,
                "age": 2,
                "data": {},
            }
        )

        # Villager production (simulated)
        for i in range(0, min(duration_seconds, 600), 30):
            events.append(
                {
                    "type": "unit_created",
                    "timestamp_ms": i * 1000,
                    "player_id": 1,
                    "data": {
                        "unit_type": "villager",
                        "unit_id": i,
                    },
                }
            )

        # Military units
        events.append(
            {
                "type": "unit_created",
                "timestamp_ms": 15 * 60 * 1000,
                "player_id": 1,
                "data": {
                    "unit_type": "archer",
                    "unit_id": 200,
                },
            }
        )

        # Building construction
        events.append(
            {
                "type": "build_completed",
                "timestamp_ms": 8 * 60 * 1000,
                "player_id": 1,
                "data": {
                    "building_type": "range",
                    "building_id": 500,
                },
            }
        )

        return sorted(events, key=lambda e: e["timestamp_ms"])


# Singleton instance for module use
_parser: ReplayParser | None = None


def get_parser(parser_type: str = "aoc_mgz") -> ReplayParser:
    """Get or create the global parser instance."""
    global _parser
    if _parser is None:
        _parser = ReplayParser(parser_type=parser_type)
    return _parser
