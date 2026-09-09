"""ORM models.

Deliberately small. The full analysis document is a self-contained blob written
once and read whole, so it lives in a JSONB column rather than being shredded
across a dozen tables. What *is* broken out into columns is exactly what we need
to query across replays: who played, what they picked, and when they aged up —
the inputs to peer comparison.

Adding a column here means committing to computing it for every replay. Metrics
that a replay cannot always answer (production timings, anything about combat)
stay inside `analysis` where their `availability` travels with them.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin

#: JSONB on Postgres, plain JSON elsewhere so the test suite can run on SQLite.
JSONDoc = JSON().with_variant(JSONB(), "postgresql")


class Replay(Base, TimestampMixin):
    """One analysed replay file."""

    __tablename__ = "replays"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: SHA-256 of the uploaded bytes. De-duplicates re-uploads of the same file.
    replay_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)

    map_name: Mapped[str | None] = mapped_column(String(255))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    game_version: Mapped[str | None] = mapped_column(String(50))

    #: The complete analysis document, as returned by the API.
    analysis: Mapped[dict] = mapped_column(JSONDoc, nullable=False, default=dict)

    players: Mapped[list[ReplayPlayer]] = relationship(
        back_populates="replay", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_replays_created_at", "created_at"),)


class ReplayPlayer(Base):
    """One player's participation, flattened for cross-replay queries."""

    __tablename__ = "replay_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    replay_pk: Mapped[int] = mapped_column(
        ForeignKey("replays.id", ondelete="CASCADE"), nullable=False
    )

    player_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    civilization: Mapped[str] = mapped_column(String(100), nullable=False)
    winner: Mapped[bool | None] = mapped_column(Boolean)

    #: Age timings in ms, or NULL where the player never reached that age.
    feudal_ms: Mapped[int | None] = mapped_column(Integer)
    castle_ms: Mapped[int | None] = mapped_column(Integer)
    imperial_ms: Mapped[int | None] = mapped_column(Integer)
    eapm: Mapped[int | None] = mapped_column(Integer)
    opening: Mapped[str | None] = mapped_column(String(50))

    replay: Mapped[Replay] = relationship(back_populates="players")

    __table_args__ = (
        Index("ix_replay_players_name", "name"),
        Index("ix_replay_players_civilization", "civilization"),
    )


__all__ = ["Base", "Replay", "ReplayPlayer"]
