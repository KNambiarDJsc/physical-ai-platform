"""ROS-002: a ROS observer is just another environment on the existing Hardware Hub, discovered by the unchanged WoT
adapter. The observer here is the observer's own Thing code replaying a snapshot RECORDED from a real ROS 2 graph
(runtimes/ros-observer/tests/fixtures); the live-graph evidence is runtimes/ros-observer/tests_ros and e2e/ros-live."""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import as_user, make_org, ok

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "runtimes" / "ros-observer" / "src"))
SNAPSHOT = ROOT / "runtimes" / "ros-observer" / "tests" / "fixtures" / "openamr-upperbody-mock.snapshot.json"
ORG = "/api/v1/orgs/robotics"
H = as_user("rin")


@pytest.fixture(scope="module")
def observer_url() -> Iterator[str]:
    from pap_ros_observer.replay import replay_server

    httpd = replay_server(SNAPSHOT)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def ros(settings_env: None, observer_url: str, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from app.config import get_settings

    catalog = [{"key": "openamr-sim", "name": "OpenAMRobot upperbody (ROS 2, read-only observer)", "kind": "simulated",
                "endpoint": observer_url}]  # fmt: skip
    monkeypatch.setenv("PAP_ENVIRONMENTS", json.dumps(catalog))
    get_settings.cache_clear()
    make_org(client, "rin", "robotics")
    ok(client.post(f"{ORG}/environments", json={"config_key": "openamr-sim"}, headers=H), 201)
    found = ok(client.post(f"{ORG}/environments/openamr-sim/discover", headers=H))
    return {"found": found, "devices": {d["key"]: d for d in found["devices"]}, "url": observer_url}


def snap() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))["things"]


def test_discovery_through_the_unchanged_adapter_finds_readable_properties_and_no_actions(ros: dict[str, Any]) -> None:
    assert ros["found"]["found"] == 2 and set(ros["devices"]) == {"ros-graph", "ros-robot"}
    for key, d in ros["devices"].items():
        caps = d["capabilities"]
        assert caps and all(c["kind"] == "property" and c["read_only"] for c in caps), key
        assert not [c for c in caps if c["kind"] == "action"], key
        assert d["declares_simulated"] is False and d["protocol"] == "wot-http" and len(d["td_sha256"]) == 64
    names = {c["name"] for c in ros["devices"]["ros-robot"]["capabilities"]}
    assert names == {"joint_states", "transforms", "controllers", "diagnostics"}


def test_live_reads_pass_through_what_the_observer_reports_without_filling_anything_in(
    client: TestClient, ros: dict[str, Any]
) -> None:
    g, r = ros["devices"]["ros-graph"]["id"], ros["devices"]["ros-robot"]["id"]
    topics = ok(client.get(f"{ORG}/devices/{g}/properties/topics", headers=H))["value"]
    assert topics == snap()["ros-graph"]["topics"]
    states = {t["state"] for t in topics}
    assert {
        "fresh",
        "stale",
        "never",
        "no_publishers",
        "latched",
    } <= states  # silence and staleness are reported as such
    stale = next(t for t in topics if t["state"] == "stale")
    assert stale["age_s"] is not None and stale["age_s"] > stale["stale_after_s"]
    joints = ok(client.get(f"{ORG}/devices/{r}/properties/joint_states", headers=H))["value"]["sources"][0]["joints"]
    assert [j["name"] for j in joints][:2] == ["lift_joint", "openarm_left_finger_joint1"] and len(joints) == 17
    clock = ok(client.get(f"{ORG}/devices/{g}/properties/clock", headers=H))["value"]
    assert clock["state"] == "absent" and clock["sim_time_s"] is None  # the mock bringup has no clock: not invented
    expected = {
        e["name"]: e["state"]
        for e in ok(client.get(f"{ORG}/devices/{g}/properties/expected_topics", headers=H))["value"]
    }
    assert expected["/clock"] == "missing"  # an expected topic that is not on the graph is "missing"


def test_a_replay_says_it_is_a_replay(client: TestClient, ros: dict[str, Any]) -> None:
    g = ros["devices"]["ros-graph"]["id"]
    c = ok(client.get(f"{ORG}/devices/{g}/properties/connectivity", headers=H))["value"]
    assert c["recorded_not_live"] is True and c["command_surface"] == "none"
    assert c["recorded_from"]["software_commit"] and c["recorded_from"]["ros_distro"] == "jazzy"


def test_no_workflow_can_be_defined_against_an_observer_device(client: TestClient, ros: dict[str, Any]) -> None:
    for i, action in enumerate(("tare", "move", "set_parameters", "joint_states")):  # the last is a property
        definition = {"steps": [{"id": "a", "device": "ros-robot", "action": action}]}
        body = {"slug": f"w{i}", "name": "x", "environment": "openamr-sim", "definition": definition}
        r = client.post(f"{ORG}/workflows", json=body, headers=H)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "workflow.unknown_action", (action, r.text)


def test_the_executors_safety_check_would_refuse_an_observer_device_anyway(ros: dict[str, Any]) -> None:
    from app.config import get_settings
    from app.hardware.models import Environment
    from app.workflows.executor import safety_check
    from pap_device_sdk import WotHttpAdapter

    env = Environment(slug="openamr-sim", name="x", kind="simulated", adapter="wot-http", config_key="openamr-sim")
    reason = safety_check(env, get_settings(), WotHttpAdapter(ros["url"]), "ros-graph")
    assert reason is not None and "did not confirm that it is simulated" in reason  # no `simulated` property to read
    physical = Environment(slug="p", name="p", kind="physical", adapter="wot-http", config_key="openamr-sim")
    assert "not configured as simulated" in (
        safety_check(physical, get_settings(), WotHttpAdapter(ros["url"]), "ros-graph") or ""
    )
