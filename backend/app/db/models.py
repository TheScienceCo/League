"""SQLAlchemy ORM models for AoE2 analytics platform."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow


# ============================================================================
# Enums
# ============================================================================


class Civilization(str, Enum):
    """AoE2 Civilizations."""

    BRITONS = "britons"
    FRANKS = "franks"
    GOTHS = "goths"
    TEUTONS = "teutons"
    JAPANESE = "japanese"
    MONGOLS = "mongols"
    VIKINGS = "vikings"
    AZTECS = "aztecs"
    MAYANS = "mayans"
    CHINESE = "chinese"
    INDIANS = "indians"
    PERSIANS = "persians"
    ETHIOPIANS = "ethiopians"
    KOREANS = "koreans"
    ITALIANS = "italians"
    PORTUGUESE = "portuguese"
    BERBERS = "berbers"
    BULGARIANS = "bulgarians"
    GEORGIANS = "georgians"
    TURKS = "turks"
    VIETNAMESE = "vietnamese"
    MALIANS = "malians"
    POLES = "poles"
    # Add more as needed


class MapType(str, Enum):
    """AoE2 Map types."""

    ARABIA = "arabia"
    NOMAD = "nomad"
    BLACK_FOREST = "black_forest"
    COASTAL = "coastal"
    CONTINENTAL = "continental"
    CUSTOM = "custom"


class GameResult(str, Enum):
    """Match result."""

    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"


class EventType(str, Enum):
    """Normalized event types from replay."""

    AGE_UP = "age_up"
    BUILD_COMPLETED = "build_completed"
    BUILD_DESTROYED = "build_destroyed"
    UNIT_CREATED = "unit_created"
    UNIT_DIED = "unit_died"
    TECHNOLOGY_RESEARCHED = "technology_researched"
    RESOURCE_TRIBUTE = "resource_tribute"
    VILLAGER_ASSIGNED = "villager_assigned"
    RESEARCH_STARTED = "research_started"
    UNIT_ATTACKED = "unit_attacked"
    FORMATION_CHANGED = "formation_changed"


class ReplayProcessingStatus(str, Enum):
    """Status of replay file processing."""

    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# Core Tables
# ============================================================================


class Player(Base, TimestampMixin):
    """A player profile."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    steam_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)

    # Stats summary (denormalized, updated periodically)
    total_games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    mean_elo: Mapped[float] = mapped_column(Float, default=1000.0)

    # Relationships
    matches: Mapped[list[MatchPlayer]] = relationship(back_populates="player")
    replays: Mapped[list[ReplayFile]] = relationship(back_populates="uploader")
    metric_percentiles: Mapped[list[PlayerMetricPercentile]] = relationship(
        back_populates="player"
    )

    __table_args__ = (Index("ix_players_username", "username"),)


class Match(Base, TimestampMixin):
    """A single match/game."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    replay_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("replay_files.id"), nullable=True
    )

    # Match metadata
    map_type: Mapped[MapType] = mapped_column(
        SQLEnum(MapType), default=MapType.ARABIA, nullable=False
    )
    map_name: Mapped[str] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    player_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Match outcome
    winner_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )

    # Patch version for reproducibility
    patch_version: Mapped[str] = mapped_column(String(50), default="latest")
    game_version: Mapped[str] = mapped_column(String(50), nullable=True)

    # Relationships
    replay_file: Mapped[ReplayFile | None] = relationship(back_populates="match")
    players: Mapped[list[MatchPlayer]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    events: Mapped[list[Event]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    game_states: Mapped[list[GameState]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    engagements: Mapped[list[Engagement]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    match_metrics: Mapped[list[MatchMetrics]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    coaching_insights: Mapped[list[CoachingInsight]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_matches_duration", "duration_seconds"),
        Index("ix_matches_created_at", "created_at"),
    )


class MatchPlayer(Base):
    """Player participation in a match."""

    __tablename__ = "match_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)

    # Player-specific match info
    civilization: Mapped[Civilization] = mapped_column(
        SQLEnum(Civilization), nullable=False
    )
    team: Mapped[int] = mapped_column(Integer, nullable=True)  # 1, 2, 3, 4 etc
    result: Mapped[GameResult] = mapped_column(
        SQLEnum(GameResult), nullable=False
    )  # Win/loss from perspective
    starting_position: Mapped[int] = mapped_column(
        Integer, nullable=True
    )  # 1-8 on standard maps
    elo_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    elo_after: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    match: Mapped[Match] = relationship(back_populates="players")
    player: Mapped[Player] = relationship(back_populates="matches")

    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_match_player"),
        Index("ix_match_players_player_id", "player_id"),
    )


class ReplayFile(Base, TimestampMixin):
    """Uploaded replay file and parsing status."""

    __tablename__ = "replay_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int | None] = mapped_column(
        ForeignKey("matches.id"), nullable=True
    )
    uploader_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )

    # File metadata
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Processing status
    status: Mapped[ReplayProcessingStatus] = mapped_column(
        SQLEnum(ReplayProcessingStatus), default=ReplayProcessingStatus.UPLOADED
    )
    parsing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parsing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    match: Mapped[Match | None] = relationship(back_populates="replay_file")
    uploader: Mapped[Player | None] = relationship(back_populates="replays")


# ============================================================================
# Event Stream & State Tables
# ============================================================================


class Event(Base):
    """Normalized event from replay event stream."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )

    # Event timing and type
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[EventType] = mapped_column(
        SQLEnum(EventType), nullable=False
    )

    # Event-specific data (JSON for flexibility)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Relationships
    match: Mapped[Match] = relationship(back_populates="events")

    __table_args__ = (
        Index("ix_events_match_id", "match_id"),
        Index("ix_events_timestamp", "timestamp_ms"),
        Index("ix_events_player_id", "player_id"),
        Index("ix_events_type", "event_type"),
    )


class GameState(Base):
    """Snapshot of game state at a point in time."""

    __tablename__ = "game_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)

    # Timing
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # State snapshot (JSON: age, resources, population, units, buildings, etc.)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Relationships
    match: Mapped[Match] = relationship(back_populates="game_states")

    __table_args__ = (
        Index("ix_game_states_match_id", "match_id"),
        Index("ix_game_states_timestamp", "timestamp_ms"),
    )


class Engagement(Base):
    """Identified military engagement/fight."""

    __tablename__ = "engagements"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)

    # Timing
    start_timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # Participants (JSON: list of player_ids involved)
    participants: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Outcome metrics
    army_value_destroyed_p1: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    army_value_destroyed_p2: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    units_killed_p1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    units_killed_p2: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Strategic value
    location: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )  # {x, y}
    strategic_value: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # "minor", "major", "critical"
    outcome: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # "favorable", "neutral", "unfavorable"

    # Relationships
    match: Mapped[Match] = relationship(back_populates="engagements")

    __table_args__ = (Index("ix_engagements_timestamp", "start_timestamp_ms"),)


# ============================================================================
# Derived Metrics Tables
# ============================================================================


class MatchMetrics(Base, TimestampMixin):
    """All calculated metrics for a match."""

    __tablename__ = "match_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id"), unique=True, nullable=False
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)

    # Feature version tracking (for reproducibility)
    feature_version: Mapped[int] = mapped_column(Integer, default=1)
    metrics_version: Mapped[str] = mapped_column(String(50), default="1.0")

    # Economy metrics
    tc_idle_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    villager_idle_time_estimated_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    resource_float_peak: Mapped[float | None] = mapped_column(Float, nullable=True)
    resource_float_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    resources_collected_total: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    # Build order metrics
    age_up_timing_ms: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )  # {feudal, castle, imperial}
    first_military_building_time_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    first_military_unit_time_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Military metrics
    military_value_killed: Mapped[float | None] = mapped_column(Float, nullable=True)
    military_value_lost: Mapped[float | None] = mapped_column(Float, nullable=True)
    military_production_uptime: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # 0-100%
    engagement_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Scouting metrics
    scouting_coverage_percent: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    time_to_enemy_discovery_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Strategic/Tactical
    reaction_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tempo_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # All metrics as JSON (flattened for search/filter)
    all_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default={})

    # Relationships
    match: Mapped[Match] = relationship(back_populates="match_metrics")


class PlayerMetricPercentile(Base, TimestampMixin):
    """Player percentile rank for a metric within an Elo cohort."""

    __tablename__ = "player_metric_percentiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)

    # Metric identification
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    elo_band_min: Mapped[int] = mapped_column(Integer, nullable=False)
    elo_band_max: Mapped[int] = mapped_column(Integer, nullable=False)

    # Peer comparison
    percentile_rank: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # 0-100, where 50 is median
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    cohort_size: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    player: Mapped[Player] = relationship(back_populates="metric_percentiles")

    __table_args__ = (
        UniqueConstraint(
            "player_id", "metric_name", "elo_band_min", name="uq_player_metric_elo"
        ),
        Index("ix_player_metric_percentiles_player_id", "player_id"),
    )


class ModelVersion(Base, TimestampMixin):
    """Tracking for ML model versions."""

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Training metadata
    training_samples: Mapped[int] = mapped_column(Integer, nullable=True)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=True
    )  # accuracy, f1, etc.

    __table_args__ = (
        UniqueConstraint("model_name", "version", name="uq_model_name_version"),
    )


# ============================================================================
# Coaching & Insights
# ============================================================================


class CoachingInsight(Base, TimestampMixin):
    """Generated coaching insight for a match."""

    __tablename__ = "coaching_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)

    # Insight classification
    category: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # "economy", "military", "build", "scouting", "timing", "reaction", "best", "worst", "expensive"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Quantification
    magnitude: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Impact severity/scale
    evidence_text: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Supporting data

    # Improvement recommendation
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_impact: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # e.g., "+5% win rate"

    # Relationships
    match: Mapped[Match] = relationship(back_populates="coaching_insights")

    __table_args__ = (Index("ix_coaching_insights_match_id", "match_id"),)
