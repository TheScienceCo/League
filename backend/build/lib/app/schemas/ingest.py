from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel


class IngestRequest(APIModel):
    riot_id: str | None = Field(
        default=None, description="Riot ID in Name#TAG form. Provide this or `puuid`."
    )
    puuid: str | None = None
    platform: str = "na1"
    count: int = Field(default=30, ge=1, le=200)
    queue: int | None = Field(default=420, description="Queue id filter; null for any")
    include_timeline: bool = True
    #: Resolving every participant's rank costs ~10 extra Riot calls per match.
    #: Off by default so an interactive request stays inside a personal key's
    #: rate limit.
    resolve_participant_ranks: bool = False
    force_refresh: bool = False


class JobResponse(APIModel):
    id: str
    puuid: str
    platform: str
    status: str
    requested_matches: int
    matches_discovered: int
    matches_ingested: int
    matches_skipped: int
    timelines_ingested: int
    features_computed: int
    progress: float
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RefreshResponse(APIModel):
    cohort_rows: int
    rce_normalized: int
    risk_cells: int
    risk_model: dict | None = None
    matches_scored: int
    roams_valued: int
    skill_gap: dict | None = None
    warnings: list[str] = Field(default_factory=list)
