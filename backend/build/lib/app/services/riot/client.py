"""HTTP client for the public Riot Games API.

Routing note: Riot splits endpoints across *platform* hosts (`na1.api...`, used
by summoner-v4) and *regional* clusters (`americas.api...`, used by account-v1
and match-v5). The client resolves the right host per method from the platform
the caller supplies, so callers only ever pass `platform="na1"`.
"""

from __future__ import annotations

from typing import Any

import httpx
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.constants import region_for_platform
from app.core.errors import NotFoundError, RateLimitedError, UpstreamError
from app.core.logging import get_logger
from app.services.riot.dto import (
    AccountDTO,
    LeagueEntryDTO,
    MatchDTO,
    SummonerDTO,
    TimelineDTO,
)
from app.services.riot.rate_limit import RiotRateLimiter, Window

log = get_logger(__name__)


class RiotAPIClient:
    """Implements `RiotProvider` against the live API."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        redis_client: aioredis.Redis | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("RIOT_API_KEY is required for the live client")
        self.api_key = api_key
        self.max_retries = max_retries if max_retries is not None else settings.riot_max_retries
        self._client = httpx.AsyncClient(
            timeout=timeout or settings.riot_timeout_seconds,
            headers={"X-Riot-Token": api_key, "Accept": "application/json"},
            transport=transport,
        )
        self._limiter = RiotRateLimiter(
            [
                Window(settings.riot_rate_limit_short, settings.riot_rate_limit_short_window),
                Window(settings.riot_rate_limit_long, settings.riot_rate_limit_long_window),
            ],
            redis_client=redis_client,
        )

    # --- plumbing ---------------------------------------------------------

    @staticmethod
    def _platform_host(platform: str) -> str:
        return f"https://{platform.lower()}.api.riotgames.com"

    @staticmethod
    def _regional_host(platform: str) -> str:
        return f"https://{region_for_platform(platform)}.api.riotgames.com"

    async def _get(self, url: str, *, route: str, params: dict[str, Any] | None = None) -> Any:
        """GET with shared rate limiting, bounded retries and error mapping.

        Retries cover 429 and 5xx only. 404 is a domain-level "no such thing"
        and is surfaced immediately as `NotFoundError`.
        """
        attempt = 0
        while True:
            await self._limiter.acquire(route)
            try:
                response = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise UpstreamError(f"network error calling Riot: {exc}") from exc
                await self._backoff(attempt)
                continue

            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                raise NotFoundError("resource not found on the Riot API", detail={"url": url})
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "1"))
                self._limiter.penalise(retry_after)
                attempt += 1
                log.warning(
                    "riot.rate_limited",
                    route=route,
                    retry_after=retry_after,
                    attempt=attempt,
                    limit_type=response.headers.get("X-Rate-Limit-Type"),
                )
                if attempt > self.max_retries:
                    raise RateLimitedError("Riot rate limit exceeded", retry_after)
                continue
            if response.status_code in {500, 502, 503, 504}:
                attempt += 1
                if attempt > self.max_retries:
                    raise UpstreamError(
                        f"Riot API returned {response.status_code}",
                        detail={"url": url},
                    )
                await self._backoff(attempt)
                continue
            if response.status_code in {401, 403}:
                raise UpstreamError(
                    "Riot rejected the API key (expired or unauthorised for this endpoint)",
                    detail={"status": response.status_code},
                )
            raise UpstreamError(
                f"unexpected Riot response {response.status_code}",
                detail={"url": url, "body": response.text[:400]},
            )

    @staticmethod
    async def _backoff(attempt: int) -> None:
        import asyncio

        await asyncio.sleep(min(2.0 ** (attempt - 1), 16.0))

    # --- endpoints --------------------------------------------------------

    async def get_account_by_riot_id(
        self, game_name: str, tag_line: str, *, platform: str
    ) -> AccountDTO:
        url = (
            f"{self._regional_host(platform)}/riot/account/v1/accounts/by-riot-id/"
            f"{httpx.URL(game_name).path.lstrip('/') or game_name}/{tag_line}"
        )
        return AccountDTO.model_validate(await self._get(url, route="account-v1"))

    async def get_account_by_puuid(self, puuid: str, *, platform: str) -> AccountDTO:
        url = f"{self._regional_host(platform)}/riot/account/v1/accounts/by-puuid/{puuid}"
        return AccountDTO.model_validate(await self._get(url, route="account-v1"))

    async def get_summoner_by_puuid(self, puuid: str, *, platform: str) -> SummonerDTO:
        url = f"{self._platform_host(platform)}/lol/summoner/v4/summoners/by-puuid/{puuid}"
        return SummonerDTO.model_validate(await self._get(url, route="summoner-v4"))

    async def get_league_entries(self, puuid: str, *, platform: str) -> list[LeagueEntryDTO]:
        """Ranked standings by PUUID.

        Riot moved this from `by-summoner/{summonerId}` to `by-puuid/{puuid}`.
        An unranked player legitimately has no entries, and some platforms return
        404 rather than an empty array, so both degrade to `[]` — the ingestion
        pipeline treats missing rank as `UNRANKED` rather than failing the job.
        """
        url = f"{self._platform_host(platform)}/lol/league/v4/entries/by-puuid/{puuid}"
        try:
            payload = await self._get(url, route="league-v4")
        except NotFoundError:
            return []
        if not isinstance(payload, list):
            return []
        return [LeagueEntryDTO.model_validate(item) for item in payload]

    async def get_match_ids(
        self,
        puuid: str,
        *,
        platform: str,
        start: int = 0,
        count: int = 20,
        queue: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[str]:
        url = f"{self._regional_host(platform)}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params: dict[str, Any] = {"start": start, "count": min(count, 100)}
        if queue is not None:
            params["queue"] = queue
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        payload = await self._get(url, route="match-v5-ids", params=params)
        return list(payload) if isinstance(payload, list) else []

    async def get_match(self, match_id: str, *, platform: str) -> MatchDTO:
        url = f"{self._regional_host(platform)}/lol/match/v5/matches/{match_id}"
        return MatchDTO.model_validate(await self._get(url, route="match-v5"))

    async def get_timeline(self, match_id: str, *, platform: str) -> TimelineDTO:
        url = f"{self._regional_host(platform)}/lol/match/v5/matches/{match_id}/timeline"
        return TimelineDTO.model_validate(await self._get(url, route="match-v5-timeline"))

    async def aclose(self) -> None:
        await self._client.aclose()
