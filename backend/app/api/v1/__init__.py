"""Version 1 of the public API."""

from fastapi import APIRouter

from app.api.v1 import health, ingest, matches, players, skillgap, spatial

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(players.router, prefix="/players", tags=["players"])
router.include_router(matches.router, prefix="/matches", tags=["matches"])
router.include_router(spatial.router, prefix="/spatial", tags=["spatial"])
router.include_router(skillgap.router, tags=["skill-gap"])
router.include_router(ingest.router, tags=["ingestion"])

__all__ = ["router"]
