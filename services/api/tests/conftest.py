from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pg import admin_url, fresh_database

API = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    cfg = Config(str(API / "alembic.ini"))
    cfg.set_main_option("script_location", str(API / "migrations"))
    cfg.attributes["url"] = url
    return cfg


@pytest.fixture(scope="session")
def pg_server() -> Iterator[str]:
    with admin_url() as url:
        yield url


@pytest.fixture(scope="session")
def database_url(pg_server: str) -> Iterator[str]:
    with fresh_database(pg_server) as url:
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture
def settings_env(database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings
    from app.engine import get_engine as get_omhs

    monkeypatch.setenv("PAP_ENV", "test")
    monkeypatch.setenv("PAP_DATABASE_URL", database_url)
    monkeypatch.setenv("PAP_AUTH_MODE", "dev")
    monkeypatch.setenv("PAP_STORAGE_PATH", str(tmp_path / "artifacts"))
    monkeypatch.setenv("PAP_WORK_PATH", str(tmp_path / "work"))
    get_settings.cache_clear()
    get_omhs.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(settings_env: None, database_url: str) -> Iterator[TestClient]:
    from app.db import get_engine
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    with get_engine(database_url).begin() as conn:
        tables = conn.execute(
            text("select tablename from pg_tables where schemaname = 'public' and tablename <> 'alembic_version'")
        ).scalars()
        names = ", ".join(f'"{t}"' for t in tables)
        if names:
            conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


def engine_required() -> bool:
    return os.environ.get("PAP_REQUIRE_ENGINE") == "1"
