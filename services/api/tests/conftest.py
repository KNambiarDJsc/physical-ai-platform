from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import as_user, make_org, ok
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
            # Identifiers cannot be bound parameters; these are table names read from pg_tables, quoted.
            conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))  # nosemgrep: pap-sql-text-interpolation


def engine_required() -> bool:
    return os.environ.get("PAP_REQUIRE_ENGINE") == "1"


@pytest.fixture(scope="session")
def virtual_lab() -> Iterator[str]:
    """The real LabThings virtual laboratory (runtimes/virtual-lab), started once per session. No mocks."""
    from pap_device_sdk.testing import run_virtual_lab

    with run_virtual_lab(Path(__file__).resolve().parents[3]) as url:
        yield url


@pytest.fixture
def with_lab(settings_env: None, virtual_lab: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """The operator catalog: the virtual lab as a simulated environment, and the same endpoint configured as a
    *physical* environment, which must allow discovery and reads but never a command (D-026)."""
    from app.config import get_settings

    catalog = [
        {"key": "virtual-lab", "name": "Virtual laboratory", "kind": "simulated", "endpoint": virtual_lab},
        {"key": "plant-floor", "name": "Plant floor (physical)", "kind": "physical", "endpoint": virtual_lab},
    ]
    monkeypatch.setenv("PAP_ENVIRONMENTS", json.dumps(catalog))
    get_settings.cache_clear()
    return virtual_lab


@pytest.fixture(scope="session")
def omhs():  # type: ignore[no-untyped-def]
    """The pinned OpenMHS engine; skipped when absent, a failure when PAP_REQUIRE_ENGINE=1."""
    from openmhs_bridge import EngineError, engine_from_env

    try:
        e = engine_from_env(Path(__file__).resolve().parents[3] / "engine.lock.json")
        e.check_binary()
    except EngineError as err:
        if engine_required():
            pytest.fail(f"PAP_REQUIRE_ENGINE=1 but the engine is unavailable: {err}")
        pytest.skip(f"engine unavailable: {err}")
    return e


DEMO_PROJECT = "/api/v1/orgs/acme/projects/picking"
DEMO = Path(__file__).resolve().parents[3] / "examples" / "manipulation-demo"


@pytest.fixture
def demo(client: TestClient, omhs: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from app.config import get_settings

    monkeypatch.setenv("PAP_WORKER_LEASE_S", "5")
    get_settings.cache_clear()
    make_org(client, "alice", "acme", "picking")
    h = as_user("alice")
    ids: dict[str, Any] = {}
    releases = (("baseline", "pick-stack-2.14.0", "2.14.0"), ("candidate", "pick-stack-2.15.0-rc1", "2.15.0-rc1"))
    for key, label, version in releases:
        comp = [{"kind": "software", "name": "pick-stack", "version": version}]
        body = {"label": label, "kind": "software", "components": comp}
        ids[key] = ok(client.post(f"{DEMO_PROJECT}/releases", json=body, headers=h), 201)["id"]
        data = (DEMO / "data" / f"{key}.csv").read_bytes()
        ids[f"{key}_art"] = ok(
            client.post(f"{DEMO_PROJECT}/artifacts", files={"file": (f"{key}.csv", data)}, headers=h), 201
        )["id"]
    spec = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
    ids["mapping"] = ok(client.post(f"{DEMO_PROJECT}/mappings", json=spec, headers=h), 201)["id"]
    ids["body"] = {
        "baseline_release_id": ids["baseline"],
        "candidate_release_id": ids["candidate"],
        "mapping_id": ids["mapping"],
        "baseline_artifact_ids": [ids["baseline_art"]],
        "candidate_artifact_ids": [ids["candidate_art"]],
        "config": {"task_type": "pick_place", "paired": True},
    }
    return ids
