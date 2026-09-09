"""Best-effort index of analysed replays in Postgres.

The disk store is the source of truth for an analysis; this table exists so that
questions spanning many replays ("every Mayans game this player has uploaded",
"median Feudal time on Arabia") are a SQL query rather than a directory walk.

Indexing is best-effort by design: an upload must not fail because Postgres is
down, since nothing about parsing or analysis needs it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Replay, ReplayPlayer

log = get_logger(__name__)


def index_analysis(session: Session, document: dict[str, Any]) -> bool:
    """Record one analysis. Returns False if it could not be stored."""
    replay_id = document["replay_id"]
    try:
        if session.scalar(select(Replay.id).where(Replay.replay_id == replay_id)):
            return True

        replay = Replay(
            replay_id=replay_id,
            filename=document["filename"],
            map_name=document.get("map_name"),
            duration_ms=document["duration_ms"],
            game_version=document.get("version"),
            analysis=document,
        )
        for p in document.get("players", []):
            ages = p.get("age_timings_ms") or {}
            eapm = (p.get("metrics") or {}).get("eapm") or {}
            replay.players.append(
                ReplayPlayer(
                    player_number=p["player_number"],
                    name=p["name"],
                    civilization=p["civilization"],
                    winner=p.get("winner"),
                    feudal_ms=ages.get("feudal"),
                    castle_ms=ages.get("castle"),
                    imperial_ms=ages.get("imperial"),
                    eapm=eapm.get("value"),
                    opening=p.get("opening"),
                )
            )
        session.add(replay)
        session.commit()
        return True
    except Exception as exc:
        # Never fail an upload over the index.
        session.rollback()
        log.warning("replay.index_failed", replay_id=replay_id, error=str(exc))
        return False
