from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app import __version__
from app.api.deps import DbSession, get_redis
from app.core.config import settings
from app.schemas.common import HealthResponse
from app.services.parser import PARSER_BACKEND

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="Liveness and dependency check")
async def health(session: DbSession) -> HealthResponse:
    database_ok = True
    try:
        session.execute(select(1))
    except Exception:
        database_ok = False

    redis_ok = False
    client = get_redis()
    if client is not None:
        try:
            redis_ok = bool(await client.ping())
        except Exception:
            redis_ok = False

    return HealthResponse(
        status="ok" if database_ok else "degraded",
        version=__version__,
        environment=settings.environment,
        database=database_ok,
        redis=redis_ok,
        replay_parser=PARSER_BACKEND,
    )
