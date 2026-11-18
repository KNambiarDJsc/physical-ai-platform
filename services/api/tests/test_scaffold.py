"""INF-002: migrations round trip on PostgreSQL, models match migrations, health, configuration guards."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import alembic_config, engine_required
from fastapi.testclient import TestClient
from pg import fresh_database
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect


def test_upgrade_downgrade_upgrade_on_empty_database(pg_server: str) -> None:
    with fresh_database(pg_server) as url:
        cfg = alembic_config(url)
        command.upgrade(cfg, "head")
        eng = create_engine(url)
        assert "projects" in inspect(eng).get_table_names()
        command.downgrade(cfg, "base")
        assert set(inspect(eng).get_table_names()) <= {"alembic_version"}
        command.upgrade(cfg, "head")
        assert "audit_events" in inspect(eng).get_table_names()
        eng.dispose()


def test_models_and_migrations_do_not_drift(database_url: str) -> None:
    from app.models import Base

    eng = create_engine(database_url)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    eng.dispose()
    assert diff == [], f"models differ from migrations; write a migration: {diff}"


def test_health_reports_database_and_engine(client: TestClient) -> None:
    r = client.get("/healthz")
    body = r.json()
    assert body["database"]["ok"] is True
    assert body["database"]["schema_revision"] is not None
    assert "engine" in body
    if body["engine"]["ok"]:
        assert r.status_code == 200 and body["status"] == "ok"
        assert body["engine"]["commit"] == "e9ef873b42f74f201aecf392ee6e61453e1f40a4"
    else:
        assert r.status_code == 503 and body["status"] == "degraded"
        assert not engine_required(), f"engine unavailable: {body['engine']}"


def test_health_is_degraded_when_the_engine_digest_is_wrong(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.engine import get_engine

    monkeypatch.setenv("OPENMHS_BIN_SHA256", "sha256:" + "0" * 64)
    get_engine.cache_clear()
    body = client.get("/healthz").json()
    assert body["engine"]["ok"] is False
    assert body["engine"]["error"] in ("engine.digest_mismatch", "engine.binary_missing")
    get_engine.cache_clear()


def test_production_refuses_dev_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("PAP_ENV", "production")
    monkeypatch.setenv("PAP_AUTH_MODE", "dev")
    with pytest.raises(ValidationError, match="refused"):
        Settings()


def test_oidc_mode_needs_issuer_and_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("PAP_AUTH_MODE", "oidc")
    monkeypatch.delenv("PAP_OIDC_ISSUER", raising=False)
    with pytest.raises(ValidationError, match="PAP_OIDC_ISSUER"):
        Settings()


def test_sqlite_is_refused() -> None:
    from app.db import get_engine

    with pytest.raises(ValueError, match="PostgreSQL"):
        get_engine("sqlite:///x.db")
