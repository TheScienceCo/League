"""Replay parsing.

`get_parser()` is the only way the rest of the app obtains a parser, so a
different backend is a one-line change here.
"""

from __future__ import annotations

from app.services.parser.mgz_parser import MgzReplayParser
from app.services.parser.types import (
    Availability,
    Command,
    CommandType,
    ParsedPlayer,
    ParsedReplay,
    ReplayParseError,
    ReplayParser,
    ResourceSample,
)

PARSER_BACKEND = MgzReplayParser.name

_parser: ReplayParser | None = None


def get_parser() -> ReplayParser:
    global _parser
    if _parser is None:
        _parser = MgzReplayParser()
    return _parser


__all__ = [
    "PARSER_BACKEND",
    "Availability",
    "Command",
    "CommandType",
    "ParsedPlayer",
    "ParsedReplay",
    "ReplayParseError",
    "ReplayParser",
    "ResourceSample",
    "get_parser",
]
