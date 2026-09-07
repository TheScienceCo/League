"""Domain exceptions and their HTTP mapping."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class RiftLabError(Exception):
    """Base class for all application errors."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, detail: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(RiftLabError):
    status_code = 404
    code = "not_found"


class ValidationError(RiftLabError):
    status_code = 422
    code = "validation_error"


class UpstreamError(RiftLabError):
    """Riot API returned an unexpected response."""

    status_code = 502
    code = "upstream_error"


class RateLimitedError(RiftLabError):
    """Riot API rate limit hit and retries exhausted."""

    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, retry_after: float = 1.0) -> None:
        super().__init__(message, detail={"retry_after": retry_after})
        self.retry_after = retry_after


class InsufficientDataError(RiftLabError):
    """Not enough observations to compute a statistic or fit a model."""

    status_code = 409
    code = "insufficient_data"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RiftLabError)
    async def _handle(request: Request, exc: RiftLabError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitedError):
            headers["Retry-After"] = str(int(exc.retry_after) or 1)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
            headers=headers,
        )
