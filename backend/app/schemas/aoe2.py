"""AoE2-specific Pydantic schemas for validation and API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models import (
    Civilization,
    EventType,
    GameResult,
    MapType,
    ReplayProcessingStatus,
)


# ============================================================================
# Enums/Exports
# ============================================================================


class CivilizationEnum(str):
    """Civilization choices."""

    pass


class MapTypeEnum(str):
    """Map type choices."""

    pass


# ============================================================================
# Common Schemas
# ============================================================================


class PaginationParams(BaseModel):
    """Pagination parameters."""

    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class TimestampedSchema(BaseModel):
    """Base schema with timestamps."""

    created_at: datetime
    updated_at: datetime


# ============================================================================
# Player Schemas
# ============================================================================


class PlayerCreate(BaseModel):
    """Create a new player."""

    username: str = Field(..., min_length=1, max_length=255)
    steam_id: int | None = None


class PlayerUpdate(BaseModel):
    """Update player info."""

    username: str | None = None


class PlayerStats(BaseModel):
    """Player statistics summary."""

    total_games: int
    wins: int
    losses: int
    win_rate: float = Field(description="Win rate as percentage (0-100)")
    mean_elo: float


class PlayerResponse(TimestampedSchema):
    """Player profile response."""

    id: int
    username: str
    steam_id: int | None = None
    stats: PlayerStats


class PlayerDetailResponse(PlayerResponse):
    """Detailed player response with metric percentiles."""

    recent_matches: list[str] = Field(default_factory=list, description="Match IDs")
    metric_summary: dict[str, float] = Field(
        default_factory=dict, description="Recent metric averages"
    )


# ============================================================================
# Match Schemas
# ============================================================================


class MatchPlayerInfo(BaseModel):
    """Info about a player in a match."""

    player_id: int
    username: str
    civilization: Civilization
    team: int | None = None
    result: GameResult
    elo_before: float | None = None
    elo_after: float | None = None


class MatchCreate(BaseModel):
    """Create a match record."""

    map_type: MapType
    duration_seconds: int = Field(..., gt=0)
    player_count: int = Field(..., ge=2, le=8)
    players: list[MatchPlayerInfo]


class MatchResponse(TimestampedSchema):
    """Match summary response."""

    id: int
    map_type: MapType
    map_name: str | None = None
    duration_seconds: int
    player_count: int
    winner_id: int | None = None
    players: list[MatchPlayerInfo]
    patch_version: str


class MatchDetailResponse(MatchResponse):
    """Detailed match response with analytics."""

    metrics: dict[int, dict[str, Any]] = Field(
        default_factory=dict, description="Per-player metrics"
    )
    coaching_report: list[dict[str, Any]] = Field(
        default_factory=list, description="Coaching insights"
    )


# ============================================================================
# Replay Schemas
# ============================================================================


class ReplayUploadRequest(BaseModel):
    """Replay upload request metadata."""

    uploader_id: int | None = None
    description: str | None = None


class ReplayUploadResponse(BaseModel):
    """Response after replay upload."""

    replay_id: int
    status: ReplayProcessingStatus
    message: str
    estimated_processing_time_seconds: int = Field(
        default=60, description="Estimated time to process"
    )


class ReplayProcessingStatus(BaseModel):
    """Current status of replay processing."""

    replay_id: int
    status: ReplayProcessingStatus
    progress_percent: int = Field(default=0, ge=0, le=100)
    message: str | None = None
    match_id: int | None = None
    error: str | None = None


class ReplayMetadata(BaseModel):
    """Metadata extracted from a replay."""

    map_type: MapType
    map_name: str | None = None
    duration_seconds: int
    player_count: int
    players: list[MatchPlayerInfo]
    patch_version: str | None = None
    game_version: str | None = None


# ============================================================================
# Events & State
# ============================================================================


class EventData(BaseModel):
    """Normalized event data."""

    type: EventType
    timestamp_ms: int
    player_id: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class GameStateSnapshot(BaseModel):
    """Game state at a point in time."""

    timestamp_ms: int
    player_id: int

    # Core state
    age: int | None = None
    resources: dict[str, int] | None = None
    population: int | None = None
    villagers: int | None = None
    military_count: int | None = None
    housing: int | None = None

    # Counts
    tc_count: int | None = None
    production_building_count: int | None = None
    unit_count: int | None = None
    building_count: int | None = None

    # Values
    army_value: float | None = None
    economy_value: float | None = None
    score: int | None = None

    # Advanced
    unit_composition: dict[str, int] | None = None
    technologies: list[str] | None = None
    map_position: dict[str, int] | None = None
    recent_engagements: list[int] | None = None

    # Inference/estimated fields
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in this state"
    )


class EngagementInfo(BaseModel):
    """Information about an identified engagement."""

    id: int
    start_timestamp_ms: int
    end_timestamp_ms: int
    participants: dict[str, Any]
    army_value_destroyed_p1: float | None = None
    army_value_destroyed_p2: float | None = None
    outcome: str | None = None


# ============================================================================
# Metrics Schemas
# ============================================================================


class EconomyMetrics(BaseModel):
    """Economy-related metrics."""

    tc_idle_time_ms: int | None = None
    resource_float_peak: float | None = None
    resource_float_average: float | None = None
    resources_collected_total: float | None = None
    villager_production_uptime: float | None = None
    resource_collection_rate: dict[str, float] | None = None


class BuildOrderMetrics(BaseModel):
    """Build order timing metrics."""

    age_up_timings_ms: dict[str, int] | None = None
    age_up_timing_deltas_ms: dict[str, int] | None = None
    first_military_building_time_ms: int | None = None
    first_military_unit_time_ms: int | None = None
    feudal_timing_delta_seconds: float | None = None
    castle_timing_delta_seconds: float | None = None


class MilitaryMetrics(BaseModel):
    """Military-related metrics."""

    military_value_killed: float | None = None
    military_value_lost: float | None = None
    military_value_ratio: float | None = None
    military_production_uptime: float | None = None
    engagement_efficiency: float | None = None
    units_killed: int | None = None
    units_lost: int | None = None


class ScoutingMetrics(BaseModel):
    """Scouting and information metrics."""

    scouting_coverage_percent: float | None = None
    time_to_enemy_discovery_ms: int | None = None
    information_advantage_rating: float | None = None


class StrategicMetrics(BaseModel):
    """Strategic and tactical metrics."""

    reaction_latency_ms: int | None = None
    tempo_score: float | None = None
    first_aggression_time_ms: int | None = None


class MatchMetricsResponse(BaseModel):
    """All metrics for a match."""

    match_id: int
    player_id: int
    feature_version: int
    metrics_version: str

    economy: EconomyMetrics = Field(default_factory=EconomyMetrics)
    build_order: BuildOrderMetrics = Field(default_factory=BuildOrderMetrics)
    military: MilitaryMetrics = Field(default_factory=MilitaryMetrics)
    scouting: ScoutingMetrics = Field(default_factory=ScoutingMetrics)
    strategic: StrategicMetrics = Field(default_factory=StrategicMetrics)

    all_metrics: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Peer Comparison Schemas
# ============================================================================


class MetricPercentileResponse(BaseModel):
    """Percentile rank for a metric within cohort."""

    metric_name: str
    percentile_rank: float = Field(..., ge=0, le=100)
    value: float | None = None
    elo_band_min: int
    elo_band_max: int
    cohort_size: int
    interpretation: str = Field(
        default="", description="Human-readable interpretation"
    )


class PeerComparisonResponse(BaseModel):
    """Peer comparison for multiple metrics."""

    player_id: int
    elo_band_min: int
    elo_band_max: int
    metrics: list[MetricPercentileResponse]


# ============================================================================
# Skill Gap Schemas
# ============================================================================


class SkillDimensionResponse(BaseModel):
    """Single skill dimension comparison."""

    dimension: str
    player_value: float
    cohort_median: float
    cohort_mean: float
    percentile_rank: float = Field(ge=0, le=100)
    estimated_elo_equivalent: int = Field(
        description="Estimated Elo if only this dimension mattered"
    )
    interpretation: str = Field(default="")


class SkillGapAnalysisResponse(BaseModel):
    """Comprehensive skill gap analysis."""

    player_id: int
    match_id: int
    overall_percentile: float = Field(ge=0, le=100)
    estimated_elo: int
    dimensions: list[SkillDimensionResponse]
    strengths: list[str] = Field(
        default_factory=list, description="Top 3-5 strongest dimensions"
    )
    weaknesses: list[str] = Field(
        default_factory=list, description="Top 3-5 weakest dimensions"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "player_id": 123,
                "match_id": 456,
                "overall_percentile": 65.0,
                "estimated_elo": 1650,
                "dimensions": [
                    {
                        "dimension": "Economy (TC idle)",
                        "player_value": 45.0,
                        "cohort_median": 120.0,
                        "cohort_mean": 135.0,
                        "percentile_rank": 72.0,
                        "estimated_elo_equivalent": 1720,
                        "interpretation": "Better than typical 1600-1800 player",
                    }
                ],
                "strengths": ["Economy", "Build timing", "Military efficiency"],
                "weaknesses": ["Scouting", "Reaction time"],
            }
        }


# ============================================================================
# Coaching Report Schemas
# ============================================================================


class CoachingReportInsight(BaseModel):
    """Single coaching insight."""

    category: str
    title: str
    description: str
    magnitude: float | None = None
    evidence_text: str | None = None
    recommendation: str | None = None
    estimated_impact: str | None = None


class CoachingReportResponse(BaseModel):
    """Complete coaching report for a match."""

    match_id: int
    player_id: int
    generated_at: datetime

    summary: str = Field(description="Brief text summary of the match")
    what_went_well: list[CoachingReportInsight] = Field(
        default_factory=list, description="Positives to reinforce"
    )
    biggest_mistakes: list[CoachingReportInsight] = Field(
        default_factory=list, description="Errors to learn from"
    )
    actionable_improvements: list[CoachingReportInsight] = Field(
        default_factory=list, description="Concrete steps to improve"
    )

    overall_grade: str = Field(
        default="", description="A, B, C, D letter grade (approximate)"
    )
    estimated_elo_performance: int = Field(
        description="What Elo level was this play"
    )
