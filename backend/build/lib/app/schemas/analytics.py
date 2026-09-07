from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class CohortDimensions(APIModel):
    team_position: str | None = None
    champion_id: int | None = None
    tier_group: str | None = None
    patch: str | None = None
    duration_bucket: str | None = None


class CohortComparisonOut(APIModel):
    metric: str
    label: str
    value: float | None = None
    percentile: float | None = None
    z_score: float | None = None
    #: Null when no cohort could be resolved for this metric at all — an explicit
    #: gap is better than a fabricated baseline.
    cohort_mean: float | None = None
    cohort_median: float | None = None
    cohort_p25: float | None = None
    cohort_p75: float | None = None
    cohort_n: int = 0
    cohort_dimensions: dict[str, Any] = Field(default_factory=dict)
    #: True when the fully specified cohort was too sparse and a broader one was
    #: used instead. Always surfaced so a caller knows what the number means.
    is_fallback_cohort: bool = False


class AdvancedStatsResponse(APIModel):
    puuid: str
    games_analyzed: int
    tier_group: str
    context: dict[str, Any] = Field(default_factory=dict)
    metrics: list[CohortComparisonOut] = Field(default_factory=list)
    #: RCE deserves its own block: it is the project's signature derived metric.
    resource_conversion: ResourceConversion | None = None


class ResourceConversion(APIModel):
    """Resource Conversion Efficiency, raw and cohort-normalised."""

    rce_raw_mean: float | None = None
    rce_z_mean: float | None = None
    damage_share_mean: float | None = None
    gold_share_mean: float | None = None
    percentile: float | None = None
    cohort_n: int | None = None
    interpretation: str | None = None


class ObservationOut(APIModel):
    metric: str
    label: str
    severity: str
    headline: str
    detail: str
    value: float | None = None
    percentile: float | None = None
    cohort_n: int
    salience: float


AdvancedStatsResponse.model_rebuild()
