"""Rate limiting for the Riot API.

Riot enforces two *application* windows simultaneously (e.g. 20 requests/second
and 100 requests/2 minutes on a personal key) plus per-method limits. We enforce
both application windows client-side with a Redis-backed sliding window so that
several worker processes share one budget, and we still honour `Retry-After`
when the server disagrees with us.

Redis is optional: without it the limiter degrades to a process-local window,
which is correct for single-process development.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Window:
    """`limit` requests per `seconds`."""

    limit: int
    seconds: int

    @property
    def key(self) -> str:
        return f"{self.limit}p{self.seconds}"


class _LocalWindow:
    """In-process sliding window used when Redis is unavailable."""

    def __init__(self, window: Window) -> None:
        self.window = window
        self._hits: deque[float] = deque()

    def wait_time(self, now: float) -> float:
        cutoff = now - self.window.seconds
        while self._hits and self._hits[0] <= cutoff:
            self._hits.popleft()
        if len(self._hits) < self.window.limit:
            return 0.0
        return self._hits[0] + self.window.seconds - now

    def record(self, now: float) -> None:
        self._hits.append(now)


#: Atomically prunes expired entries, checks the count, and records a hit.
#: Returns 0 when admitted, otherwise the milliseconds to wait.
_LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now_ms - window_ms)
local count = redis.call('ZCARD', key)
if count < limit then
  redis.call('ZADD', key, now_ms, member)
  redis.call('PEXPIRE', key, window_ms)
  return 0
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local wait = (tonumber(oldest[2]) + window_ms) - now_ms
if wait < 1 then wait = 1 end
return wait
"""


class RiotRateLimiter:
    """Shared client-side limiter across one or more application windows."""

    def __init__(
        self,
        windows: list[Window],
        *,
        redis_client: aioredis.Redis | None = None,
        namespace: str = "riot:rl",
    ) -> None:
        self.windows = windows
        self._redis = redis_client
        self._namespace = namespace
        self._local = {w.key: _LocalWindow(w) for w in windows}
        self._lock = asyncio.Lock()
        self._script: Any | None = None
        self._counter = 0
        #: Set when Riot returns 429; blocks all callers until it passes.
        self._penalty_until = 0.0

    async def _ensure_script(self) -> None:
        if self._redis is not None and self._script is None:
            self._script = self._redis.register_script(_LUA_SLIDING_WINDOW)

    async def acquire(self, route: str = "global") -> None:
        """Block until a request slot is available in every window."""
        while True:
            now = time.monotonic()
            penalty = self._penalty_until - now
            if penalty > 0:
                await asyncio.sleep(min(penalty, 10.0))
                continue

            wait = await self._try_acquire(route)
            if wait <= 0:
                return
            await asyncio.sleep(min(wait, 10.0))

    async def _try_acquire(self, route: str) -> float:
        if self._redis is not None:
            try:
                return await self._acquire_redis(route)
            except Exception as exc:  # pragma: no cover - redis outage path
                log.warning("rate_limiter.redis_failed", error=str(exc))
                self._redis = None
        return await self._acquire_local()

    async def _acquire_redis(self, route: str) -> float:
        await self._ensure_script()
        assert self._script is not None
        now_ms = time.time() * 1000.0
        self._counter += 1
        member = f"{now_ms:.3f}:{self._counter}"
        for window in self.windows:
            key = f"{self._namespace}:{route}:{window.key}"
            wait_ms = await self._script(
                keys=[key],
                args=[now_ms, window.seconds * 1000, window.limit, member],
            )
            if int(wait_ms) > 0:
                return float(wait_ms) / 1000.0
        return 0.0

    async def _acquire_local(self) -> float:
        async with self._lock:
            now = time.monotonic()
            waits = [w.wait_time(now) for w in self._local.values()]
            longest = max(waits) if waits else 0.0
            if longest > 0:
                return longest
            for w in self._local.values():
                w.record(now)
            return 0.0

    def penalise(self, retry_after_seconds: float) -> None:
        """Called on a 429 so every in-flight caller backs off together."""
        self._penalty_until = max(
            self._penalty_until, time.monotonic() + max(retry_after_seconds, 1.0)
        )
