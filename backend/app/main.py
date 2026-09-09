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
from app.services.parser import PARSER_BACKEND

log = get_logger(__name__)

DESCRIPTION = """
Age of Empires II replay analytics.

Upload an `.aoe2record` file and get back timings, build order, a banked-resource
curve and plain-language observations about the game.

**What a replay can and cannot tell you.** A replay is a *command stream* — the
inputs players sent to the engine, not the outcomes the engine produced. Age
advances, buildings placed and technologies researched are all recorded. Unit
deaths, kills and combat results are **not present in the file at all**, so this
API does not report them.

Every metric therefore carries an `availability`:

* `observed` — read directly from the command stream.
* `reconstructed` — derived from observed commands under a stated assumption.
* `inferred` — from DE sync packets, whose field meanings are community
  reverse-engineered rather than documented. Directionally right, not exact.
* `unavailable` — not recoverable. The value is `null`, never zero.

Some replay versions also fail to decode unit-queue commands; when that happens
production metrics become `unavailable` and the response carries a `warning`
saying so.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info(
        "app.startup",
        environment=settings.environment,
        replay_parser=PARSER_BACKEND,
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
