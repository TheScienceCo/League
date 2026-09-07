"""Test fixtures.

The suite runs against SQLite by default so `pytest` needs no containers; set
`TEST_DATABASE_URL` to point it at a real Postgres when you want to exercise the
production dialect. The models use `with_variant` types precisely so both work,
and no query in the codebase depends on a Postgres-only operator.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("RIOT_USE_MOCK", "true")
os.environ.setdefault("REDIS_URL", "")

from app.db.models import Base
from app.db.session import get_db
from app.services.riot.mock import MockRiotProvider

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")


def scope_for(session: Session) -> Callable[[], AbstractContextManager[Session]]:
    """A session scope over the test session.

    Flushes rather than commits: the fixture owns the transaction and rolls it
    back, so each test starts from a clean schema.
    """

    @contextmanager
    def _scope() -> Iterator[Session]:
        yield session
        session.flush()

    return _scope


@pytest.fixture(scope="session")
def engine():  # type: ignore[no-untyped-def]
    from sqlalchemy.pool import StaticPool

    if TEST_DATABASE_URL.startswith("sqlite"):
        eng = create_engine(
            TEST_DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        eng = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    """A session on a clean schema for each test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def provider() -> MockRiotProvider:
    return MockRiotProvider()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """API client wired to the test session."""
    from app.main import create_app

    app = create_app()

    def _override_db() -> Iterator[Session]:
        # FastAPI calls the dependency and drives it as a generator; handing back
        # a bare iterator is not the same thing.
        yield db

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_db(db: Session, provider: MockRiotProvider) -> Session:
    """A small corpus, ingested through the real pipeline.

    Uses the actual `IngestionService` rather than hand-built rows so the tests
    exercise the same path production does.
    """
    import asyncio

    from app.services.ingest import pipeline as pipeline_module

    service = pipeline_module.IngestionService(provider, session_scope=scope_for(db))

    async def run() -> None:
        for name in ("TestAlpha", "TestBravo", "TestCharlie"):
            puuid = await service.resolve_riot_id(f"{name}#NA1", "na1")
            await service.ingest_player(
                puuid,
                "na1",
                pipeline_module.IngestOptions(
                    count=4, resolve_participant_ranks=True, concurrency=1
                ),
            )

    asyncio.run(run())
    db.flush()
    return db
