"""Test fixtures.

The suite runs against SQLite by default so `pytest` needs no containers; set
`TEST_DATABASE_URL` to point it at a real Postgres when you want to exercise the
production dialect. The models use `with_variant` types precisely so both work.

Replay fixtures under `tests/fixtures/` are real `.aoe2record` files. Parsing is
tested against real replays rather than synthetic bytes because the whole risk in
this codebase is mis-reading a real file format.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("REDIS_URL", "")

from app.db.models import Base
from app.db.session import get_db

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")

FIXTURES = Path(__file__).parent / "fixtures"

#: Queue commands decode; production metrics available.
REC_WITH_QUEUE = FIXTURES / "de-25.02.aoe2record"
#: Queue commands do not decode; production metrics must be `unavailable`.
REC_WITHOUT_QUEUE = FIXTURES / "de-62.0.aoe2record"
#: Too old for the parser; must raise rather than crash.
REC_UNPARSEABLE = FIXTURES / "de-13.03.aoe2record"


@pytest.fixture
def engine():
    """A fresh database per test, so no test can see another's rows."""
    # FastAPI runs sync endpoints in a threadpool, so an in-memory SQLite
    # database needs a single shared connection that permits cross-thread use.
    kwargs: dict = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        kwargs = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    eng = create_engine(TEST_DATABASE_URL, future=True, **kwargs)
    # An in-memory SQLite engine starts empty, but a real Postgres database
    # persists between tests - so drop first, or rows leak across the suite.
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    s = factory()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def client(session, tmp_path, monkeypatch) -> Iterator[TestClient]:
    """An API client with an isolated on-disk analysis store."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "replay_storage_path", str(tmp_path / "replays"))
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def rec_with_queue() -> bytes:
    return REC_WITH_QUEUE.read_bytes()


@pytest.fixture
def rec_without_queue() -> bytes:
    return REC_WITHOUT_QUEUE.read_bytes()
