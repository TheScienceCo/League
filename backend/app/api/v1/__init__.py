"""Version 1 of the public API."""

from fastapi import APIRouter

from app.api.v1 import health, replays

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(replays.router, prefix="/replays", tags=["replays"])

__all__ = ["router"]
