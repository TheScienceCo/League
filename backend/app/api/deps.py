"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

DbSession = Annotated[Session, Depends(get_db)]

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis | None:
    """A shared Redis client, or `None` when Redis is not configured.

    Redis is a performance aid here (replay-job queue, response cache), never a
    correctness requirement — every caller degrades gracefully.
    """
    global _redis
    if _redis is None and settings.redis_url:
        try:
            _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            return None
    return _redis


def pagination(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> tuple[int, int]:
    return limit, offset


PaginationDep = Annotated[tuple[int, int], Depends(pagination)]


def db_session() -> Iterator[Session]:
    yield from get_db()
