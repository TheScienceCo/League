"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import router as v1_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)

DESCRIPTION = """
Post-game League of Legends analytics and coaching.

Every figure this API returns is **derived** — differentials against the lane
opponent, shares, rates, cohort percentiles, and model outputs. Raw Riot fields
are stored but are not the product.

**Scope and compliance.** All analysis is retrospective, over match history and
timeline data that a player can already see for their own games. There are no
live-game or spectator endpoints, nothing is exposed that a player could not
have known at the time, and no model input uses hidden enemy information. See
`docs/COMPLIANCE.md`.

**Reading the numbers.** Metrics whose name includes `risk`, `expected`, or which
appear under `skill-gap` and `dva` are model estimates. They describe association
within a historical dataset, not causation, and each response carries the caveats
that apply to it.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info(
        "app.startup",
        environment=settings.environment,
        riot_provider="simulated" if settings.use_mock_riot else "riot-api",
    )
    yield
    log.info("app.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "api": settings.api_v1_prefix,
        }

    return app


app = create_app()
