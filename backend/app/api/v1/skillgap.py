"""Skill Gap Analysis endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.skillgap import RankSeparationResponse, SkillGapResponse
from app.services.ml.skill_gap import analyze_player, rank_separation_summary

router = APIRouter()


@router.get(
    "/players/{puuid}/skill-gap",
    response_model=SkillGapResponse,
    summary="Behaviours separating this player from a target rank band",
)
def get_skill_gap(
    puuid: str,
    session: DbSession,
    target_tier_group: Annotated[str | None, Query()] = None,
    top_n: Annotated[int, Query(ge=1, le=20)] = 5,
) -> SkillGapResponse:
    report = analyze_player(session, puuid, target_tier_group=target_tier_group, top_n=top_n)
    return SkillGapResponse.model_validate(report.to_dict())


@router.get(
    "/skill-gap/rank-separation",
    response_model=RankSeparationResponse,
    summary="Which measured behaviours separate rank bands overall",
)
def get_rank_separation(
    session: DbSession,
    top_n: Annotated[int, Query(ge=1, le=40)] = 15,
) -> RankSeparationResponse:
    return RankSeparationResponse.model_validate(rank_separation_summary(session, top_n=top_n))
