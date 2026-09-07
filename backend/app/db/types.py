"""Portable column types.

Postgres is the production database, but the test-suite runs against SQLite so
that `pytest` needs no containers. These aliases use the rich Postgres type when
the dialect supports it and fall back to JSON otherwise; no query in the codebase
relies on Postgres-only array/JSON operators, so the two behave identically.
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Integer
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.types import TypeEngine

JSONVariant: TypeEngine[object] = JSON().with_variant(JSONB(), "postgresql")
IntArray: TypeEngine[object] = JSON().with_variant(ARRAY(Integer()), "postgresql")

#: A 64-bit autoincrementing primary key.
#:
#: SQLite only auto-assigns rowids for a column declared exactly `INTEGER
#: PRIMARY KEY`; a `BIGINT` one is just a normal column and inserts fail on the
#: NOT NULL constraint. The variant keeps BIGINT on Postgres — where the
#: timeline tables genuinely need the range — and falls back to INTEGER on
#: SQLite so the test-suite can run without a container.
BigIntPK: TypeEngine[int] = BigInteger().with_variant(Integer(), "sqlite")
