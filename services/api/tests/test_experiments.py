"""SIM-002..004: immutable experiment specs, request/approve/execute through the workflow engine, capture.

Nothing is mocked: the simulation host is runtimes/sim-host with its selftest catalog in a subprocess, discovery and
reads go through the real adapter, trials execute through the worker's own claim/execute functions, and every verdict
is the pinned engine's (`openmhs outcome verify`). The selftest-drive scenario is a stated kinematic model, not a
simulator; Gazebo is SIM-006.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import add_member, as_user, make_org, ok
from pap_device_sdk.testing import run_sim_host

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "runtimes" / "sim-host" / "catalogs" / "selftest.json"
ORG = "/api/v1/orgs/lab"
ADA, BOB, VIC = as_user("ada"), as_user("bob"), as_user("vic")  # engineer-admin, engineer, viewer
LIMIT_M = 0.15  # the contract's threshold in drive_spec; the test checks the engine applied it, not what it decided

pytestmark = pytest.mark.engine


def configure(monkeypatch: pytest.MonkeyPatch, endpoint: str) -> None:
    from app.config import get_settings

    catalog = [
        {"key": "selftest-sim", "name": "Self-test simulation host", "kind": "simulated", "endpoint": endpoint},
        {"key": "sim-as-physical", "name": "Same host, declared physical", "kind": "physical", "endpoint": endpoint},
    ]
    monkeypatch.setenv("PAP_ENVIRONMENTS", json.dumps(catalog))
    get_settings.cache_clear()


@pytest.fixture
def lab(client: TestClient, sim_host: str, omhs: Any, monkeypatch: pytest.MonkeyPatch) -> str:
    configure(monkeypatch, sim_host)
    make_org(client, "ada", "lab")
    add_member(client, "ada", "lab", "bob", "engineer")
    add_member(client, "ada", "lab", "vic", "viewer")
    for key in ("selftest-sim", "sim-as-physical"):
        ok(client.post(f"{ORG}/environments", json={"config_key": key}, headers=ADA), 201)
        ok(client.post(f"{ORG}/environments/{key}/discover", headers=ADA))
    ok(client.post(f"{ORG}/experiments", json={"slug": "stop", "name": "Stop on command loss"}, headers=ADA), 201)
    return sim_host


def listing(client: TestClient, env: str = "selftest-sim") -> dict[str, Any]:
    envs = {e["slug"]: e for e in ok(client.get(f"{ORG}/simulation-environments", headers=VIC))}
    return envs[env]


def scenario(client: TestClient, sid: str) -> dict[str, Any]:
    return next(s for s in listing(client)["scenarios"] if s["id"] == sid)


def drive_spec(client: TestClient, **over: Any) -> dict[str, Any]:
    env = listing(client)
    sc = next(s for s in env["scenarios"] if s["id"] == "selftest-drive")
    spec: dict[str, Any] = {
        "environment": "selftest-sim",
        "simulator": env["simulator"],
        "scenario": {"id": "selftest-drive", "version": "1", "definition_sha256": sc["definition_sha256"]},
        "software": [{"name": "selftest-drive", "revision": "1"}],
        "initial_conditions": {"speed_mps": 0.3, "drive_s": 1.0},
        "seeds": [3, 11],
        "repetitions": 2,
        "arms": [
            {"key": "pre-fix", "role": "baseline", "parameters": {"stop_on_command_loss": False}},
            {"key": "fix", "role": "candidate", "parameters": {"stop_on_command_loss": True}},
        ],
        "limits": {"max_trials": 8, "max_wall_time_s": 600},
        "observations": {"measurements": ["travel_after_kill_m", "driven_before_kill_m"], "artifacts": ["recording"]},
        "contract": {
            "name": "stop-on-command-loss",
            "version": "1",
            "conditions": [
                {
                    "name": f"travel after command loss at most {LIMIT_M} m",
                    "measurement": "travel_after_kill_m",
                    "op": "le",
                    "value": LIMIT_M,
                }
            ],
        },
    }
    spec.update(over)
    return spec


def new_version(client: TestClient, spec: dict[str, Any], status: int = 201, headers: Any = ADA) -> Any:
    return ok(client.post(f"{ORG}/experiments/stop/versions", json={"spec": spec}, headers=headers), status)


def refused(client: TestClient, spec: dict[str, Any]) -> tuple[int, str, str]:
    r = client.post(f"{ORG}/experiments/stop/versions", json={"spec": spec}, headers=ADA)
    detail = r.json().get("detail")
    if isinstance(detail, dict):
        return r.status_code, detail.get("code", ""), detail.get("message", "")
    return r.status_code, "", json.dumps(detail)


def work_all(limit: int = 20) -> list[str]:
    from app.config import get_settings
    from app.db import session_factory
    from app.workflows import service
    from app.workflows.executor import execute_run

    done = []
    for _ in range(limit):
        with session_factory()() as s:
            run_id = service.claim(s, "test-worker", get_settings().worker_lease_s)
        if run_id is None:
            break
        done.append(execute_run(run_id, "test-worker"))
    return done


def runs(client: TestClient) -> list[dict[str, Any]]:
    return ok(client.get(f"{ORG}/workflow-runs", headers=VIC))


# ------------------------------------------------------------------------------------------------- SIM-002


def test_the_environment_lists_what_its_host_offers_now(client: TestClient, lab: str) -> None:
    envs = {e["slug"]: e for e in ok(client.get(f"{ORG}/simulation-environments", headers=VIC))}
    assert set(envs) == {"selftest-sim"}  # the same host configured as physical is never offered here (D-026)
    env = envs["selftest-sim"]
    assert env["state"] == "ready" and env["simulator"]["kind"] == "selftest"
    sc = {s["id"]: s for s in env["scenarios"]}["selftest-drive"]
    assert sc["parameters_schema"]["required"] == ["stop_on_command_loss"]
    assert [o["name"] for o in sc["outputs"]] == ["travel_after_kill_m", "driven_before_kill_m"]
    assert sc["definition_sha256"].startswith("sha256:") and "command" not in sc


def test_a_version_is_its_content_checksum_and_is_never_edited(client: TestClient, lab: str) -> None:
    spec = drive_spec(client)
    v1 = new_version(client, spec)
    assert v1["number"] == 1
    canon = json.dumps(v1["spec"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert v1["spec_sha256"] == "sha256:" + hashlib.sha256(canon.encode()).hexdigest()  # computed by the platform
    assert v1["spec"]["schema"] == "pap.experiment-spec/1" and v1["spec"]["approval"]["distinct_approver"] is True
    again = new_version(client, copy.deepcopy(spec), status=200)
    assert (again["number"], again["spec_sha256"]) == (1, v1["spec_sha256"])
    changed = new_version(client, drive_spec(client, initial_conditions={"speed_mps": 0.4, "drive_s": 1.0}))
    assert changed["number"] == 2 and changed["spec_sha256"] != v1["spec_sha256"]
    assert ok(client.get(f"{ORG}/experiments/stop/versions/1", headers=VIC))["spec"] == v1["spec"]
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(f"{ORG}/experiments/stop/versions/1", headers=ADA).status_code == 405
    status, code, _ = refused(client, {**spec, "spec_sha256": "sha256:" + "0" * 64})
    assert (status, code) == (422, "experiment.invalid")  # a client cannot supply the checksum


@pytest.mark.parametrize(
    ("change", "status", "code", "says"),
    [
        (lambda s: s.update(environment="sim-as-physical"), 422, "experiment.not_simulated", "not a simulated"),
        (lambda s: s["scenario"].update(id="selftest-nope"), 422, "experiment.unknown_scenario", "does not list"),
        (lambda s: s["arms"][1]["parameters"].update(command_timeout_s=5), 422, "experiment.parameters", "arm fix"),
        (lambda s: s["arms"][0]["parameters"].update(wiring="--main"), 422, "experiment.parameters", "wiring"),
        (lambda s: s["simulator"].update(name="Gazebo"), 409, "experiment.simulator_changed", "host reports"),
        (
            lambda s: s["scenario"].update(definition_sha256="sha256:" + "1" * 64),
            409,
            "experiment.scenario_changed",
            "",
        ),
        (lambda s: s.update(seeds=[1]), 422, "experiment.invalid", "one seed per repetition"),
        (lambda s: s["arms"][0]["parameters"].update(drive_s=2), 422, "experiment.invalid", "redefines"),
        (lambda s: s["observations"].update(measurements=["speed"]), 422, "experiment.observations", "speed"),
        (lambda s: s["observations"].update(artifacts=["video"]), 422, "experiment.observations", "video"),
        (lambda s: s["contract"]["conditions"][0].update(measurement="sum"), 422, "experiment.contract", "sum"),
        (lambda s: s["limits"].update(max_trials=3), 422, "experiment.limits", "4 trials exceed"),
        (lambda s: s["limits"].update(max_wall_time_s=60), 422, "experiment.limits", "above the limit"),
        (lambda s: s["observations"].update(recording="recording"), 422, "experiment.invalid", "model"),
        (
            lambda s: s.update(model={"project": "nope", "model": "base", "version": 1}),
            422,
            "experiment.model",
            "no model version",
        ),
    ],
)
def test_a_version_is_refused_with_the_reason(
    client: TestClient, lab: str, change: Any, status: int, code: str, says: str
) -> None:
    spec = drive_spec(client)
    change(spec)
    got = refused(client, spec)
    assert got[:2] == (status, code), got
    assert says in got[2], got


def test_seeds_need_a_seed_parameter_and_arms_are_validated_per_seed(client: TestClient, lab: str) -> None:
    sc = scenario(client, "selftest-sum")
    spec = drive_spec(
        client,
        scenario={"id": "selftest-sum", "version": "1", "definition_sha256": sc["definition_sha256"]},
        initial_conditions={"b": 1},
        arms=[{"key": "one", "parameters": {"a": 1}}],
        observations={"measurements": ["sum"], "artifacts": ["telemetry"]},
        contract={
            "name": "sum",
            "version": "1",
            "conditions": [{"name": "sum is 2", "measurement": "sum", "op": "eq", "value": 2}],
        },
    )
    assert refused(client, spec)[:2] == (422, "experiment.seeds")
    spec.update(seeds=[], repetitions=1)
    assert new_version(client, spec)["number"] == 1


def test_roles_and_workspaces(client: TestClient, lab: str) -> None:
    spec = drive_spec(client)
    r = client.post(f"{ORG}/experiments/stop/versions", json={"spec": spec}, headers=VIC)
    assert r.status_code == 403  # viewers read, engineers create
    new_version(client, spec)
    assert ok(client.get(f"{ORG}/experiments/stop", headers=VIC))["versions"][0]["number"] == 1
    make_org(client, "eve", "other")
    assert client.get(f"{ORG}/experiments/stop", headers=as_user("eve")).status_code == 404
    assert client.get("/api/v1/orgs/other/experiments/stop", headers=as_user("eve")).status_code == 404


# ------------------------------------------------------------------------------------------------- SIM-003


def request(client: TestClient, number: int = 1, headers: Any = VIC) -> dict[str, Any]:
    return ok(
        client.post(f"{ORG}/experiments/stop/versions/{number}/requests", json={"note": "please"}, headers=headers), 201
    )


def decide(client: TestClient, rid: str, what: str, sha: str, headers: Any = BOB, status: int = 200) -> Any:
    body = ok(
        client.post(f"{ORG}/experiment-requests/{rid}/{what}", json={"spec_sha256": sha}, headers=headers), status
    )
    return body["detail"] if status >= 400 else body


def test_only_an_approval_of_the_exact_checksum_by_someone_else_queues_trials(client: TestClient, lab: str) -> None:
    v = new_version(client, drive_spec(client))
    v2 = new_version(client, drive_spec(client, repetitions=1, seeds=[5]))
    req = request(client, headers=ADA)  # anyone in the workspace may ask; ada asks, so ada may not approve
    assert req["state"] == "awaiting_approval" and req["trials"] == 0 and runs(client) == []
    rid = req["id"]
    assert (
        client.post(
            f"{ORG}/experiment-requests/{rid}/approve", json={"spec_sha256": v["spec_sha256"]}, headers=VIC
        ).status_code
        == 403
    )
    assert (
        decide(client, rid, "approve", v["spec_sha256"], headers=ADA, status=403)["code"] == "experiment.self_approval"
    )
    assert decide(client, rid, "approve", v2["spec_sha256"], status=409)["code"] == "experiment.checksum"
    assert runs(client) == []
    out = decide(client, rid, "approve", v["spec_sha256"])
    assert out["state"] == "approved" and out["decided_by"] and out["requested_by"] != out["decided_by"]
    assert out["trials"] == 4 and {r["state"] for r in runs(client)} == {"queued"}
    assert decide(client, rid, "approve", v["spec_sha256"], status=409)["code"] == "experiment.decided"
    # one workflow per arm and seed; the seed is part of the step input
    wfs = [w for w in ok(client.get(f"{ORG}/workflows", headers=VIC)) if w["template"] == "experiment"]
    assert len(wfs) == 4
    inputs = sorted((w["parameters"]["arm"], w["definition"]["steps"][0]["input"]["parameters"]["seed"]) for w in wfs)
    assert inputs == [("fix", 3), ("fix", 11), ("pre-fix", 3), ("pre-fix", 11)]
    step = wfs[0]["definition"]["steps"][0]
    assert step["device"] == "simulation-host" and step["action"] == "run_scenario"
    assert step["timeout_s"] == scenario(client, "selftest-drive")["max_duration_s"] + 60


def test_a_rejected_request_never_runs(client: TestClient, lab: str) -> None:
    v = new_version(client, drive_spec(client))
    rid = request(client)["id"]
    out = decide(client, rid, "reject", v["spec_sha256"])
    assert out["state"] == "rejected" and out["trials"] == 0
    assert decide(client, rid, "approve", v["spec_sha256"], status=409)["code"] == "experiment.decided"
    assert runs(client) == [] and work_all() == []


def test_trials_execute_through_the_worker_and_the_verdicts_are_the_engines(client: TestClient, lab: str) -> None:
    v = new_version(client, drive_spec(client))
    rid = request(client)["id"]
    decide(client, rid, "approve", v["spec_sha256"])
    assert work_all() == ["succeeded"] * 4
    d = ok(client.get(f"{ORG}/experiment-requests/{rid}", headers=VIC))
    assert d["trials_done"] == 4
    for t in d["trial_results"]:
        assert t["state"] == "succeeded" and t["seed"] in (3, 11)
        travel = t["measurements"]["travel_after_kill_m"]
        # the relation between the measurement and the engine's verdict over the spec's contract, not an outcome
        assert t["verdict"] == ("SATISFIED" if travel <= LIMIT_M else "VIOLATED"), t
        assert t["host_run"]["identity"]["seed"] == t["seed"]
        run = ok(client.get(f"{ORG}/workflow-runs/{t['run_id']}", headers=VIC))
        cond = run["verification"]["contract"]["conditions"][0]
        assert cond["op"] == "le" and cond["value"] == {"value": LIMIT_M, "unit": "m"}
        assert run["provenance"]["evidence_class"] == "simulated"
    arms = {a["arm"]: a for a in d["arms"]}
    assert [a["arm"] for a in d["arms"]] == ["pre-fix", "fix"] and arms["pre-fix"]["role"] == "baseline"
    for a in d["arms"]:
        assert a["trials"] == 2 and sum(a["verdicts"].values()) == 2 and len(a["values"]["travel_after_kill_m"]) == 2
        assert not {"mean", "p_value", "ci95", "difference"} & set(a)  # raw values only: no statistic here


def test_a_long_step_keeps_its_lease_while_it_waits(
    client: TestClient, lab: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings
    from app.db import session_factory
    from app.workflows import service
    from app.workflows.executor import execute_run
    from app.workflows.models import WorkflowRun

    monkeypatch.setenv("PAP_WORKER_LEASE_S", "5")
    get_settings.cache_clear()
    sc = scenario(client, "selftest-sleep")
    spec = drive_spec(
        client,
        scenario={"id": "selftest-sleep", "version": "1", "definition_sha256": sc["definition_sha256"]},
        initial_conditions={},
        seeds=[],
        repetitions=1,
        arms=[{"key": "wait", "parameters": {"seconds": 4}}],
        observations={"measurements": ["slept_s"], "artifacts": []},
        contract={
            "name": "waited",
            "version": "1",
            "conditions": [{"name": "waited", "measurement": "slept_s", "op": "ge", "value": 3.9}],
        },
    )
    v = new_version(client, spec)
    rid = request(client)["id"]
    decide(client, rid, "approve", v["spec_sha256"])
    with session_factory()() as s:
        run_id = service.claim(s, "test-worker", 5)
        assert run_id is not None
        first = s.get(WorkflowRun, run_id).lease_expires_at  # type: ignore[union-attr]
    result: list[str] = []
    th = threading.Thread(target=lambda: result.append(execute_run(run_id, "test-worker")))
    th.start()
    seen = []
    while th.is_alive():
        with session_factory()() as s:
            r = s.get(WorkflowRun, run_id)
            assert r is not None
            if r.lease_expires_at is not None:
                seen.append(r.lease_expires_at)
        time.sleep(0.5)
    th.join()
    assert result == ["succeeded"]
    assert max(seen) > first  # renewed while the host was still running the scenario
    with session_factory()() as s:
        r = s.get(WorkflowRun, run_id)
        assert r is not None and r.attempts == 1


def test_a_changed_host_listing_invalidates_approval(
    client: TestClient, lab: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    v = new_version(client, drive_spec(client))
    rid = request(client)["id"]
    # The operator edits the scenario without bumping its version and serves the edited catalog at the same key.
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    for s in cat["scenarios"]:
        if s["id"] == "selftest-drive":
            s["max_duration_s"] = 25
    edited = tmp_path / "catalogs" / "edited.json"
    edited.parent.mkdir()
    edited.write_text(json.dumps(cat), encoding="utf-8")
    shutil.copytree(CATALOG.parent.parent / "selftest", tmp_path / "selftest")
    with run_sim_host(ROOT, edited, work=tmp_path / "work") as other:
        configure(monkeypatch, other)
        out = decide(client, rid, "approve", v["spec_sha256"], status=409)
        assert out["code"] == "experiment.scenario_changed"
    assert (
        runs(client) == []
        and ok(client.get(f"{ORG}/experiment-requests/{rid}", headers=VIC))["state"] == "awaiting_approval"
    )
