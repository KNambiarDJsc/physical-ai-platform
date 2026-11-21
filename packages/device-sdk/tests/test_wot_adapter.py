"""The WoT/LabThings adapter against the real virtual laboratory (a LabThings-FastAPI server in a subprocess)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from pap_device_sdk import AdapterError, WotHttpAdapter
from pap_device_sdk.testing import run_virtual_lab
from pap_device_sdk.wot import parse_td

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def lab() -> Iterator[str]:
    with run_virtual_lab(ROOT) as url:
        yield url


def rid() -> str:
    return uuid.uuid4().hex


def test_discovery_describes_every_instrument_and_its_capabilities(lab: str) -> None:
    devices = {d.key: d for d in WotHttpAdapter(lab).discover()}
    assert set(devices) == {"pump", "balance", "simulation"}
    pump = devices["pump"]
    assert pump.declares_simulated and pump.protocol == "wot-http"
    actions = {a.name: a for a in pump.affordances if a.kind == "action"}
    assert actions["dispense"].idempotency_key == "request_id"
    assert actions["dispense"].input_schema["required"] == ["volume_ul", "request_id"]
    props = {a.name: a for a in devices["balance"].affordances if a.kind == "property"}
    assert props["mass_g"].read_only and props["mass_g"].data_schema["type"] == "number"
    # The digest ignores `base`, so it is stable across discoveries and hosts.
    assert WotHttpAdapter(lab).discover()[1].td_sha256 == devices["pump"].td_sha256


def test_actions_run_and_a_repeated_request_id_has_no_second_effect(lab: str) -> None:
    a = WotHttpAdapter(lab)
    assert a.invoke_action("simulation", "reset", {}).status == "completed"
    assert a.invoke_action("balance", "tare", {}).status == "completed"
    key = rid()
    inv = a.invoke_action("pump", "dispense", {"volume_ul": 50.0, "request_id": key})
    assert inv.status == "completed" and inv.output["reported_dispensed_ul"] == 50.0
    first = a.invoke_action("balance", "weigh", {}).output["mass_g"]
    assert 0.0490 < first < 0.0508  # 50 µL of water ≈ 0.0499 g
    again = a.invoke_action("pump", "dispense", {"volume_ul": 50.0, "request_id": key})
    assert again.status == "completed" and again.output["repeated"] == "true"
    second = a.invoke_action("balance", "weigh", {}).output["mass_g"]
    assert abs(second - first) < 0.0005  # noise only: nothing was dispensed the second time


def test_invalid_input_is_refused_before_anything_starts(lab: str) -> None:
    inv = WotHttpAdapter(lab).invoke_action("pump", "dispense", {"volume_ul": -5, "request_id": rid()})
    assert inv.status == "error" and not inv.accepted and "volume_ul" in (inv.error or "")


def test_a_fault_changes_what_happens_not_what_the_pump_reports(lab: str) -> None:
    a = WotHttpAdapter(lab)
    a.invoke_action("simulation", "reset", {})
    a.invoke_action("simulation", "set_fault", {"fault": "partial_blockage"})
    a.invoke_action("balance", "tare", {})
    inv = a.invoke_action("pump", "dispense", {"volume_ul": 100.0, "request_id": rid()})
    assert inv.output["reported_dispensed_ul"] == 100.0
    measured = a.invoke_action("balance", "weigh", {}).output["mass_g"]
    assert 0.055 < measured < 0.070  # about 62 µL arrived
    assert a.read_property("pump", "simulated") is True
    a.invoke_action("simulation", "reset", {})


def test_links_outside_the_configured_endpoint_are_refused() -> None:
    td = {
        "title": "Rogue",
        "actions": {"go": {"forms": [{"href": "http://169.254.169.254/latest/meta-data", "op": ["invokeaction"]}]}},
        "properties": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "lab.local", "the adapter must never contact another host"
        return httpx.Response(200, json={"rogue": td})

    a = WotHttpAdapter("http://lab.local:8100", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert parse_td("rogue", td).title == "Rogue"
    with pytest.raises(AdapterError, match="outside the configured endpoint"):
        a.invoke_action("rogue", "go", {})
