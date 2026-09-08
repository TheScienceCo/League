"""AoE2 match analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

log_router = APIRouter()


@log_router.get("/{match_id}")
async def get_match(match_id: int):
    """Get basic match information."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


@log_router.get("/{match_id}/detail")
async def get_match_detail(match_id: int):
    """Get detailed match analysis including metrics and coaching."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


@log_router.get("/{match_id}/metrics/{player_id}")
async def get_match_metrics(match_id: int, player_id: int):
    """Get calculated metrics for a player in a match."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


@log_router.get("/{match_id}/timeline/{player_id}")
async def get_match_timeline(
    match_id: int,
    player_id: int,
    interval_seconds: int = 10,
):
    """Get game state timeline for a player."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


@log_router.get("/{match_id}/events/{player_id}")
async def get_match_events(
    match_id: int,
    player_id: int,
    event_type: str | None = None,
):
    """Get events for a player in a match."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )


router = log_router
