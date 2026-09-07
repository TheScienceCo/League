from __future__ import annotations

from pydantic import Field

from app.schemas.common import APIModel


class RiskCell(APIModel):
    cell_x: int
    cell_y: int
    grid_size: int
    phase: str
    role: str
    tier_group: str
    exposures: int
    deaths: int
    risk: float
    baseline_risk: float
    #: risk / baseline_risk — "how much more dangerous than average is this cell".
    lift: float
    zone: str | None = None


class HeatmapResponse(APIModel):
    grid_size: int
    horizon_seconds: int
    role: str | None = None
    phase: str | None = None
    tier_group: str | None = None
    cells: list[RiskCell] = Field(default_factory=list)
    #: Always present: these are model/empirical estimates, not measurements.
    disclaimer: str


class ZoneRiskOut(APIModel):
    zone: str
    phase: str
    exposures: int
    deaths: int
    risk: float
    baseline_risk: float
    lift: float
    insight: str | None = None


class ZoneRiskResponse(APIModel):
    role: str | None = None
    tier_group: str | None = None
    horizon_seconds: int
    zones: list[ZoneRiskOut] = Field(default_factory=list)
    disclaimer: str


class PlayerExposureCell(APIModel):
    cell_x: int
    cell_y: int
    exposures: int
    deaths: int
    death_rate: float


class PlayerDeath(APIModel):
    match_id: str
    minute: int
    x: float
    y: float
    zone: str


class PlayerSpatialResponse(APIModel):
    puuid: str
    grid_size: int
    matches: int
    cells: list[PlayerExposureCell] = Field(default_factory=list)
    deaths: list[PlayerDeath] = Field(default_factory=list)
    #: The player's own risk profile compared against a higher rank band.
    comparison: SpatialComparison | None = None
    disclaimer: str


class SpatialComparison(APIModel):
    player_tier_group: str
    reference_tier_group: str
    player_high_risk_share: float | None = None
    reference_high_risk_share: float | None = None
    player_deaths_above_expected: float | None = None
    zones: list[ZoneRiskOut] = Field(default_factory=list)


PlayerSpatialResponse.model_rebuild()
