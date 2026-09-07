"""Single-match analysis."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.core.errors import InsufficientDataError
from app.schemas.match import MatchAnalysisResponse
from app.services.analytics.dva import DEFAULT_HORIZONS, DVAEngine
from app.services.analytics.match_analysis import analyze_match

router = APIRouter()


@router.get(
    "/{match_id}",
    response_model=MatchAnalysisResponse,
    summary="Full analysis of one match from one player's perspective",
)
def get_match_analysis(
    match_id: str,
    puuid: Annotated[str, Query(description="Which player to analyse the match for")],
    session: DbSession,
    include_risk: Annotated[bool, Query()] = True,
) -> MatchAnalysisResponse:
    return MatchAnalysisResponse.model_validate(
        analyze_match(session, match_id, puuid, include_risk=include_risk)
    )


@router.get(
    "/{match_id}/dva",
    summary="Decision Value Added for one player in one match (experimental)",
)
def get_match_dva(
    match_id: str,
    puuid: Annotated[str, Query()],
    session: DbSession,
    horizon_seconds: Annotated[int, Query(description="30, 60 or 120")] = 60,
) -> dict[str, Any]:
    """Estimate the value of a player's decisions across the match.

    Returns 409 with an explanation when the DVA models have not been trained —
    they need a corpus, and returning zeros would be worse than saying so.
    """
    if horizon_seconds not in DEFAULT_HORIZONS:
        horizon_seconds = 60
    engine = DVAEngine.load(session)
    if engine is None:
        raise InsufficientDataError(
            "DVA models have not been trained yet; run `riftlab refresh-analytics --dva`"
        )
    report = engine.evaluate(
        session, match_id=match_id, puuid=puuid, horizon_seconds=horizon_seconds
    )
    return report.to_dict()
