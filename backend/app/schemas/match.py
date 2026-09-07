from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class MatchListItem(APIModel):
    match_id: str
    queue_id: int
    queue_name: str
    patch: str
    game_start: str | None = None
    duration_seconds: int
    win: bool
    champion_id: int
    champion_name: str | None = None
    team_position: str
    kills: int
    deaths: int
    assists: int
    cs: int
    cs_per_min: float | None = None
    gold_earned: int
    vision_score: int
    kill_participation: float | None = None
    gold_diff_10: float | None = None
    gold_diff_15: float | None = None
    rce_raw: float | None = None
    has_timeline: bool = False


class MatchAnalysisResponse(APIModel):
    """The full single-match analysis payload.

    Kept as loosely typed dicts for the nested collections: the shape is defined
    by `services.analytics.match_analysis` and mirrored in the frontend's
    TypeScript types, and duplicating a dozen nested models here would only add a
    second place to keep in sync.
    """

    match: dict[str, Any]
    player: dict[str, Any]
    lane_opponent: dict[str, Any] | None = None
    teams: list[dict[str, Any]] = Field(default_factory=list)
    participants: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    deaths: list[dict[str, Any]] = Field(default_factory=list)
    objective_setups: list[dict[str, Any]] = Field(default_factory=list)
    roams: list[dict[str, Any]] = Field(default_factory=list)
    advanced_metrics: list[dict[str, Any]] = Field(default_factory=list)
    cohort_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
