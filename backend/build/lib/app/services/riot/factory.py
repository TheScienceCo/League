"""Provider selection.

Callers ask for a `RiotProvider` and get either the live HTTP client or the
simulator, decided purely by configuration. Nothing downstream branches on it.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger
from app.services.riot.client import RiotAPIClient
from app.services.riot.mock import MockRiotProvider
from app.services.riot.protocol import RiotProvider

log = get_logger(__name__)


def get_riot_provider(*, redis_client: aioredis.Redis | None = None) -> RiotProvider:
    if settings.use_mock_riot:
        log.info(
            "riot.provider.mock",
            reason="RIOT_USE_MOCK is set" if settings.riot_use_mock else "no RIOT_API_KEY",
        )
        return MockRiotProvider()
    log.info("riot.provider.live", platform=settings.riot_platform)
    return RiotAPIClient(settings.riot_api_key, redis_client=redis_client)
