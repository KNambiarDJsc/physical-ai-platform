"""A real PostgreSQL for tests: PAP_TEST_DATABASE_URL if set (CI service container), else a local pgserver.

Each test session gets its own freshly created database, dropped at the end. SQLite is never used.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

REPO = Path(__file__).resolve().parents[3]


@contextmanager
def admin_url() -> Iterator[str]:
    """A URL (SQLAlchemy form) of a server we may create databases on."""
    url = os.environ.get("PAP_TEST_DATABASE_URL")
    if url:
        yield url
        return
    import pgserver  # dev dependency (decision D-006)

    data = Path(os.environ.get("PAP_TEST_PGDATA", REPO / "var" / "test-pg"))
    data.mkdir(parents=True, exist_ok=True)
    srv = pgserver.get_server(str(data), cleanup_mode="stop")
    try:
        yield srv.get_uri().replace("postgresql://", "postgresql+psycopg://", 1)
    finally:
        srv.cleanup()


def _libpq(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


@contextmanager
def fresh_database(server_url: str) -> Iterator[str]:
    name = f"pap_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(_libpq(server_url), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    url = make_url(server_url).set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        from app.db import get_engine

        get_engine.cache_clear()
        with psycopg.connect(_libpq(server_url), autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
