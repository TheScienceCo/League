from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class BehaviourGapOut(APIModel):
    feature: str
    label: str
    #: Permutation importance in the rank-separation model, normalised to sum 1.
    importance: float
    #: Univariate Spearman correlation with rank, for contrast with `importance`.
    rank_correlation: float
    player_value: float | None = None
    player_residual: float | None = None
    target_residual: float | None = None
    #: Gap in pooled standard deviations; positive means the target tier is better.
    gap_z: float
    #: The same gap in natural units, on the same controlled basis as `gap_z`.
    gap_natural: float
    #: The target band's raw, uncontrolled average — context, not a like-for-like
    #: comparison against `player_value`.
    target_band_average: float | None = None
    #: importance x max(gap_z, 0) — the ranking key.
    impact: float
    higher_is_better: bool
    player_percentile: float | None = None
    cohort_n: int | None = None


class SkillGapResponse(APIModel):
    puuid: str
    player_tier_group: str
    target_tier_group: str
    games_analyzed: int
    behaviours: list[BehaviourGapOut] = Field(default_factory=list)
    model: dict[str, Any] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)


class RankSeparationBehaviour(APIModel):
    feature: str
    label: str
    importance: float
    rank_correlation: float
    higher_is_better: bool
    tier_means: dict[str, float | None] = Field(default_factory=dict)


class RankSeparationResponse(APIModel):
    model: dict[str, Any] = Field(default_factory=dict)
    behaviours: list[RankSeparationBehaviour] = Field(default_factory=list)
