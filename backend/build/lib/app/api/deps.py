"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import VALID_PLATFORMS
from app.core.errors import ValidationError
from app.db.session import get_db
from app.services.riot import RiotProvider, get_riot_provider

DbSession = Annotated[Session, Depends(get_db)]

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis | None:
    """A shared Redis client, or `None` when Redis is not configured.

    Redis is a performance aid here (response cache, shared rate-limit budget),
    never a correctness requirement — every caller degrades gracefully.
    """
    global _redis
    if _redis is None and settings.redis_url:
        try:
            _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            return None
    return _redis


def provider() -> RiotProvider:
    return get_riot_provider(redis_client=get_redis())


RiotDep = Annotated[RiotProvider, Depends(provider)]


def validated_platform(
    platform: Annotated[str | None, Query(description="Platform host, e.g. na1")] = None,
) -> str:
    value = (platform or settings.riot_platform).lower()
    if value not in VALID_PLATFORMS:
        raise ValidationError(
            f"unknown platform {value!r}",
            detail={"valid": sorted(VALID_PLATFORMS)},
        )
    return value


PlatformDep = Annotated[str, Depends(validated_platform)]


def pagination(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> tuple[int, int]:
    return limit, offset


PaginationDep = Annotated[tuple[int, int], Depends(pagination)]


def db_session() -> Iterator[Session]:
    yield from get_db()


def request_session_scope(session: Session) -> Callable[[], AbstractContextManager[Session]]:
    """A session scope bound to the current request.

    Handed to `IngestionService` for work that must be visible to the rest of the
    request — resolving a Riot ID, say. Background ingestion deliberately does
    *not* use this: the request session is closed once the response is sent.
    """

    @contextmanager
    def _scope() -> Iterator[Session]:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    return _scope
