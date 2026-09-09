"""API schemas for replay analysis.

These mirror `app.services.analysis.metrics` one-for-one. Note that every metric
carries its own `availability`: the API never returns a bare number without
saying how it was obtained, because a replay cannot answer every question asked
of it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.parser.types import Availability


class MetricOut(BaseModel):
    key: str
    label: str
    value: float | int | None
    unit: str
    availability: Availability
    note: str | None = None


class BuildOrderEntry(BaseModel):
    timestamp_ms: int
    building: str
    x: float | None = None
    y: float | None = None


class ResourcePoint(BaseModel):
    timestamp_ms: int
    banked: int = Field(description="Food + wood + gold + stone combined.")
    objects: int


class PlayerAnalysisOut(BaseModel):
    player_number: int
    name: str
    civilization: str
    winner: bool | None = None
    opening: str | None = None
    age_timings_ms: dict[str, int] = Field(default_factory=dict)
    float_by_age: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, MetricOut] = Field(default_factory=dict)
    build_order: list[BuildOrderEntry] = Field(default_factory=list)
    resource_curve: list[ResourcePoint] = Field(default_factory=list)
    insights: list[str] = Field(
        default_factory=list,
        description="Plain-language observations, each tied to a measured value.",
    )


class MatchAnalysisOut(BaseModel):
    replay_id: str = Field(description="SHA-256 of the uploaded file; stable and de-duplicating.")
    filename: str
    map_name: str | None = None
    duration_ms: int
    version: str | None = None
    players: list[PlayerAnalysisOut] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=list,
        description="Parse-quality problems that limit which metrics are available.",
    )


class ReplayListItem(BaseModel):
    replay_id: str
    filename: str
    map_name: str | None = None
    duration_ms: int
    players: list[str] = Field(default_factory=list)
