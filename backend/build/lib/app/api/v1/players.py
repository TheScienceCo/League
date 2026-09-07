"""Player search, profile, match list, advanced stats and cohort comparison."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import (
    DbSession,
    PaginationDep,
    PlatformDep,
    RiotDep,
    request_session_scope,
)
from app.core.errors import NotFoundError
from app.db.models import Summoner
from app.schemas.analytics import AdvancedStatsResponse
from app.schemas.common import Page
from app.schemas.match import MatchListItem
from app.schemas.player import PlayerProfile, PlayerSummary
from app.services.analytics import player as player_service
from app.services.analytics.spatial import player_exposure_heatmap, zone_risk_table
from app.services.ingest.pipeline import IngestionService

router = APIRouter()

RISK_DISCLAIMER = (
    "Risk figures are model estimates derived from historical match data. They "
    "describe association, not causation, and are not predictions about a live game."
)


@router.get("/search", response_model=PlayerSummary, summary="Resolve a Riot ID to a player")
async def search_player(
    riot_id: Annotated[str, Query(description="Riot ID in Name#TAG form")],
    platform: PlatformDep,
    session: DbSession,
    provider: RiotDep,
) -> PlayerSummary:
    """Resolve and persist an account.

    This performs identity lookups only — it does not ingest matches. Ingestion
    is an explicit, asynchronous action (`POST /ingest`) because it is the
    expensive part and the caller should decide when to pay for it.
    """
    # Identity resolution writes through the request's own session so the row is
    # readable below; match ingestion is a separate, background concern.
    service = IngestionService(provider, session_scope=request_session_scope(session))
    puuid = await service.resolve_riot_id(riot_id, platform)
    summoner = session.get(Summoner, puuid)
    if summoner is None:
        raise NotFoundError(f"could not resolve {riot_id}")
    return PlayerSummary(
        puuid=summoner.puuid,
        game_name=summoner.game_name,
        tag_line=summoner.tag_line,
        platform=summoner.platform,
        profile_icon_id=summoner.profile_icon_id,
        summoner_level=summoner.summoner_level,
        last_ingested_at=summoner.last_ingested_at,
        ranks=player_service.player_ranks(session, puuid),  # type: ignore[arg-type]
    )


@router.get("", response_model=list[PlayerSummary], summary="List ingested players")
def list_players(
    session: DbSession,
    pagination: PaginationDep,
    tier_group: Annotated[str | None, Query()] = None,
) -> list[PlayerSummary]:
    limit, offset = pagination
    stmt = select(Summoner).order_by(Summoner.last_ingested_at.desc().nullslast())
    rows = list(session.scalars(stmt.limit(limit).offset(offset)))
    out: list[PlayerSummary] = []
    for row in rows:
        ranks = player_service.player_ranks(session, row.puuid)
        if tier_group and not any(r["tier_group"] == tier_group for r in ranks):
            continue
        out.append(
            PlayerSummary(
                puuid=row.puuid,
                game_name=row.game_name,
                tag_line=row.tag_line,
                platform=row.platform,
                profile_icon_id=row.profile_icon_id,
                summoner_level=row.summoner_level,
                last_ingested_at=row.last_ingested_at,
                ranks=ranks,  # type: ignore[arg-type]
            )
        )
    return out


@router.get("/{puuid}", response_model=PlayerProfile, summary="Player dashboard")
def get_profile(puuid: str, session: DbSession) -> PlayerProfile:
    return PlayerProfile.model_validate(player_service.build_profile(session, puuid))


@router.get(
    "/{puuid}/matches",
    response_model=Page[MatchListItem],
    summary="Match history with derived per-game metrics",
)
def get_matches(puuid: str, session: DbSession, pagination: PaginationDep) -> Page[MatchListItem]:
    limit, offset = pagination
    items, total = player_service.build_match_list(session, puuid, limit=limit, offset=offset)
    return Page[MatchListItem](
        items=[MatchListItem.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{puuid}/advanced",
    response_model=AdvancedStatsResponse,
    summary="Advanced derived statistics against peer cohorts",
)
def get_advanced(
    puuid: str,
    session: DbSession,
    metrics: Annotated[list[str] | None, Query(description="Restrict to these metrics")] = None,
) -> AdvancedStatsResponse:
    return AdvancedStatsResponse.model_validate(
        player_service.build_advanced_stats(session, puuid, metrics=metrics)
    )


@router.get("/{puuid}/cohort", summary="Side-by-side comparison against a target rank band")
def get_cohort_comparison(
    puuid: str,
    session: DbSession,
    target_tier_group: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return player_service.cohort_comparison_table(
        session, puuid, target_tier_group=target_tier_group
    )


@router.get("/{puuid}/trend", summary="Rolling performance trend over recent games")
def get_trend(
    puuid: str,
    session: DbSession,
    window: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[dict[str, Any]]:
    return player_service.performance_trend(session, puuid, window=window)


@router.get("/{puuid}/spatial", summary="Where this player stands, and where they die")
def get_player_spatial(
    puuid: str,
    session: DbSession,
    limit_matches: Annotated[int, Query(ge=1, le=200)] = 40,
    reference_tier_group: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    payload = player_exposure_heatmap(session, puuid, limit_matches=limit_matches)
    features = player_service.player_features(session, puuid)
    context = player_service.player_context(features)
    own_band = context.get("tier_group") or "UNRANKED"

    from app.core.constants import TIER_GROUP_ORDER

    if reference_tier_group is None:
        idx = TIER_GROUP_ORDER.index(own_band) if own_band in TIER_GROUP_ORDER else 0
        reference_tier_group = TIER_GROUP_ORDER[min(idx + 1, len(TIER_GROUP_ORDER) - 1)]

    high_risk = [
        f.high_risk_exposure_share for f in features if f.high_risk_exposure_share is not None
    ]
    dae = [f.deaths_above_expected for f in features if f.deaths_above_expected is not None]

    reference_zones = zone_risk_table(
        session,
        role=context.get("team_position"),
        tier_group=reference_tier_group,
    )
    payload["comparison"] = {
        "player_tier_group": own_band,
        "reference_tier_group": reference_tier_group,
        "player_high_risk_share": (sum(high_risk) / len(high_risk)) if high_risk else None,
        "reference_high_risk_share": None,
        "player_deaths_above_expected": (sum(dae) / len(dae)) if dae else None,
        "zones": [
            {
                "zone": z.zone,
                "phase": z.phase,
                "exposures": z.exposures,
                "deaths": z.deaths,
                "risk": z.risk,
                "baseline_risk": z.baseline_risk,
                "lift": z.lift,
                "insight": None,
            }
            for z in reference_zones[:8]
        ],
    }
    payload["puuid"] = puuid
    payload["disclaimer"] = RISK_DISCLAIMER
    return payload
