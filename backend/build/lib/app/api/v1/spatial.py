"""Map risk heatmaps and region insights."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.core.config import settings
from app.schemas.spatial import HeatmapResponse, RiskCell, ZoneRiskOut, ZoneRiskResponse
from app.services.analytics.spatial import heatmap_cells, zone_risk_table

router = APIRouter()

DISCLAIMER = (
    "Estimated from historical match timelines. Values describe association "
    "between position and subsequent deaths, not causation, and are intended for "
    "post-game review rather than live decision-making."
)


@router.get("/heatmap", response_model=HeatmapResponse, summary="Death-risk heatmap")
def get_heatmap(
    session: DbSession,
    role: Annotated[str | None, Query(description="TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY")] = None,
    phase: Annotated[str | None, Query(description="EARLY/MID/LATE")] = None,
    tier_group: Annotated[str | None, Query()] = None,
    min_exposures: Annotated[int, Query(ge=1)] = 10,
) -> HeatmapResponse:
    cells = heatmap_cells(
        session,
        role=role,
        phase=phase,
        tier_group=tier_group,
        min_exposures=min_exposures,
    )
    return HeatmapResponse(
        grid_size=settings.risk_model_grid_size,
        horizon_seconds=settings.risk_horizon_seconds,
        role=role,
        phase=phase,
        tier_group=tier_group,
        cells=[RiskCell.model_validate(c) for c in cells],
        disclaimer=DISCLAIMER,
    )


@router.get("/zones", response_model=ZoneRiskResponse, summary="Risk by named map region")
def get_zone_risk(
    session: DbSession,
    role: Annotated[str | None, Query()] = None,
    tier_group: Annotated[str | None, Query()] = None,
    min_exposures: Annotated[int, Query(ge=1)] = 30,
) -> ZoneRiskResponse:
    """Region-level risk, with a plain-language reading of each lift.

    The phrasing is deliberately associational — "associated with", never
    "causes" — because that is all an observational comparison supports.
    """
    zones = zone_risk_table(session, role=role, tier_group=tier_group, min_exposures=min_exposures)
    out: list[ZoneRiskOut] = []
    for z in zones:
        insight = None
        if z.lift >= 1.25 or z.lift <= 0.8:
            direction = "higher" if z.lift > 1 else "lower"
            phase_label = {"EARLY": "the early game", "MID": "mid game", "LATE": "late game"}.get(
                z.phase, z.phase
            )
            insight = (
                f"Being in {z.zone.replace('_', ' ').lower()} during {phase_label} is "
                f"associated with a {z.lift:.1f}x {direction} probability of dying within "
                f"{settings.risk_horizon_seconds}s, compared with the average position for "
                f"this role and phase (n={z.exposures:,} observations)."
            )
        out.append(
            ZoneRiskOut(
                zone=z.zone,
                phase=z.phase,
                exposures=z.exposures,
                deaths=z.deaths,
                risk=z.risk,
                baseline_risk=z.baseline_risk,
                lift=z.lift,
                insight=insight,
            )
        )
    return ZoneRiskResponse(
        role=role,
        tier_group=tier_group,
        horizon_seconds=settings.risk_horizon_seconds,
        zones=out,
        disclaimer=DISCLAIMER,
    )
