"""Hardware Hub (HUB-001): environments from the operator catalog, discovery against the real virtual laboratory,
capabilities, live reads, roles."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import add_member, as_user, make_org, ok

ORG = "/api/v1/orgs/lab"


@pytest.fixture
def lab_org(client: TestClient, with_lab: str) -> dict[str, Any]:
    return make_org(client, "ada", "lab")


def connect(client: TestClient, key: str = "virtual-lab", **extra: Any) -> dict[str, Any]:
    return ok(client.post(f"{ORG}/environments", json={"config_key": key, **extra}, headers=as_user("ada")), 201)


def test_only_operator_environments_can_be_connected(
    client: TestClient, lab_org: dict[str, Any], with_lab: str
) -> None:
    catalog = ok(client.get("/api/v1/environment-catalog", headers=as_user("ada")))
    assert [(c["key"], c["kind"]) for c in catalog] == [("virtual-lab", "simulated"), ("plant-floor", "physical")]
    r = client.post(f"{ORG}/environments", json={"config_key": "elsewhere"}, headers=as_user("ada"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_environment"
    # A URL in the request is not an input: the endpoint always comes from the operator's catalog.
    env = connect(client, endpoint="http://169.254.169.254/latest")
    assert env["endpoint"] == with_lab and env["kind"] == "simulated" and env["available"]
    r = client.post(f"{ORG}/environments", json={"config_key": "virtual-lab"}, headers=as_user("ada"))
    assert r.status_code == 409


def test_discovery_records_devices_capabilities_and_digests(client: TestClient, lab_org: dict[str, Any]) -> None:
    connect(client)
    d = ok(client.post(f"{ORG}/environments/virtual-lab/discover", headers=as_user("ada")))
    assert (d["found"], d["new"], d["changed"], d["missing"]) == (3, 3, 0, 0)
    devices = {x["key"]: x for x in d["devices"]}
    assert set(devices) == {"pump", "balance", "simulation"}
    pump = devices["pump"]
    assert pump["declares_simulated"] and pump["protocol"] == "wot-http" and len(pump["td_sha256"]) == 64
    caps = {(c["kind"], c["name"]): c for c in pump["capabilities"]}
    dispense = caps[("action", "dispense")]
    assert dispense["idempotency_key"] == "request_id"
    assert dispense["input_schema"]["properties"]["volume_ul"]["maximum"] == 1000
    assert caps[("property", "simulated")]["read_only"]
    again = ok(client.post(f"{ORG}/environments/virtual-lab/discover", headers=as_user("ada")))
    assert (again["found"], again["new"], again["changed"], again["missing"]) == (3, 0, 0, 0)
    envs = ok(client.get(f"{ORG}/environments", headers=as_user("ada")))
    assert envs[0]["devices"] == 3 and envs[0]["last_discovered_at"]
    detail = ok(client.get(f"{ORG}/devices/{pump['id']}", headers=as_user("ada")))
    assert detail["description_document"]["@context"].startswith("https://www.w3.org/2022/wot/td")


def test_a_device_that_disappears_is_kept_and_marked_missing(client: TestClient, lab_org: dict[str, Any]) -> None:
    from app.db import session_factory
    from app.hardware.models import Device, Environment
    from app.hardware.service import record_discovery
    from pap_device_sdk import WotHttpAdapter
    from sqlalchemy import select

    connect(client)
    ok(client.post(f"{ORG}/environments/virtual-lab/discover", headers=as_user("ada")))
    env_row = ok(client.get(f"{ORG}/environments", headers=as_user("ada")))[0]
    found = [f for f in WotHttpAdapter(env_row["endpoint"]).discover() if f.key != "balance"]
    with session_factory()() as s:
        env = s.get(Environment, __import__("uuid").UUID(env_row["id"]))
        assert env is not None
        summary = record_discovery(s, env, found)
        s.commit()
        assert summary.missing == 1
        balance = s.scalar(select(Device).where(Device.environment_id == env.id, Device.key == "balance"))
        assert balance is not None and balance.present is False
    devices = {x["key"]: x for x in ok(client.get(f"{ORG}/devices", headers=as_user("ada")))}
    assert devices["balance"]["present"] is False and devices["pump"]["present"] is True


def test_properties_are_read_live(client: TestClient, lab_org: dict[str, Any]) -> None:
    connect(client)
    devices = {
        x["key"]: x
        for x in ok(client.post(f"{ORG}/environments/virtual-lab/discover", headers=as_user("ada")))["devices"]
    }
    r = ok(client.get(f"{ORG}/devices/{devices['pump']['id']}/properties/simulated", headers=as_user("ada")))
    assert r["value"] is True and r["read_at"]
    r = ok(client.get(f"{ORG}/devices/{devices['balance']['id']}/properties/readability_g", headers=as_user("ada")))
    assert r["value"] == 0.0001
    assert (
        client.get(f"{ORG}/devices/{devices['pump']['id']}/properties/nope", headers=as_user("ada")).status_code == 404
    )


def test_roles_and_a_physical_environment_is_still_observable(client: TestClient, lab_org: dict[str, Any]) -> None:
    add_member(client, "ada", "lab", "vic", "viewer")
    add_member(client, "ada", "lab", "eve", "engineer")
    assert (
        client.post(f"{ORG}/environments", json={"config_key": "virtual-lab"}, headers=as_user("vic")).status_code
        == 403
    )
    assert (
        client.post(f"{ORG}/environments", json={"config_key": "virtual-lab"}, headers=as_user("eve")).status_code
        == 403
    )
    connect(client, "plant-floor")
    assert client.post(f"{ORG}/environments/plant-floor/discover", headers=as_user("vic")).status_code == 403
    d = ok(client.post(f"{ORG}/environments/plant-floor/discover", headers=as_user("eve")))
    assert d["found"] == 3 and all(x["environment_kind"] == "physical" for x in d["devices"])
    assert len(ok(client.get(f"{ORG}/devices", headers=as_user("vic")))) == 3


def test_an_environment_the_operator_withdrew_is_unavailable(
    client: TestClient, lab_org: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    connect(client)
    monkeypatch.setenv("PAP_ENVIRONMENTS", json.dumps([]))
    get_settings.cache_clear()
    assert ok(client.get(f"{ORG}/environments", headers=as_user("ada")))[0]["available"] is False
    r = client.post(f"{ORG}/environments/virtual-lab/discover", headers=as_user("ada"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "environment_unavailable"
