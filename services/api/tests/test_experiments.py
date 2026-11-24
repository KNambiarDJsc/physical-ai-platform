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
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import add_member, as_user, make_org, ok
from pap_device_sdk.testing import run_sim_host
from test_agent_tools import api_url  # noqa: F401  (a pytest fixture: the real API served over HTTP)

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


def configure_env(monkeypatch: pytest.MonkeyPatch, endpoint: str, key: str, name: str) -> None:
    """The operator catalog with one simulated environment at ``endpoint``."""
    from app.config import get_settings

    monkeypatch.setenv(
        "PAP_ENVIRONMENTS", json.dumps([{"key": key, "name": name, "kind": "simulated", "endpoint": endpoint}])
    )
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
    new_version(client, drive_spec(client, approval={"role": "engineer", "distinct_approver": False}), status=422)
    v = new_version(client, drive_spec(client))
    v2 = new_version(client, drive_spec(client, repetitions=1, seeds=[5]))
    req = request(client, headers=ADA)  # anyone in the workspace may ask; ada asks, so ada may not approve
    assert req["state"] == "awaiting_approval" and req["trials"] == 0 and runs(client) == []
    rid = req["id"]
    assert req["requested_by_me"] is True  # the API says who asked, relative to the caller
    assert ok(client.get(f"{ORG}/experiment-requests/{rid}", headers=BOB))["requested_by_me"] is False
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


# ------------------------------------------------------------------------------------------------- SIM-004

PROJECT = f"{ORG}/projects/robots"


def with_model(client: TestClient) -> dict[str, Any]:
    """A registered robot model version (the toy one the isolation test uses) in a project of the workspace."""
    from test_isolation import TOY_MANIFEST, TOY_STL, TOY_URDF

    ok(client.post(f"{ORG}/projects", json={"slug": "robots", "name": "Robots"}, headers=ADA), 201)
    ok(
        client.post(
            f"{PROJECT}/twin/models",
            data={"manifest": json.dumps(TOY_MANIFEST)},
            files=[("files", ("robot.urdf", TOY_URDF, "application/xml")), ("files", ("a.stl", TOY_STL, "model/stl"))],
            headers=ADA,
        ),
        201,
    )
    return {"project": "robots", "model": TOY_MANIFEST["slug"], "version": 1}


def recording_spec(client: TestClient, **over: Any) -> dict[str, Any]:
    spec = drive_spec(
        client,
        model=with_model(client),
        observations={
            "measurements": ["travel_after_kill_m"],
            "artifacts": ["recording"],
            "recording": "recording",
        },
    )
    spec.update(over)
    return spec


def approved(client: TestClient, spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    v = new_version(client, spec)
    rid = request(client, v["number"])["id"]
    decide(client, rid, "approve", v["spec_sha256"])
    return rid, v


def capture() -> int:
    """Capture every finished trial, as the worker does across its idle polls (five per call)."""
    from app.experiments.capture import capture_ready

    total = 0
    while n := capture_ready():
        total += n
    return total


def trials_of(client: TestClient, rid: str) -> list[dict[str, Any]]:
    return ok(client.get(f"{ORG}/experiment-requests/{rid}", headers=VIC))["trial_results"]


def test_captured_artifacts_are_checked_stored_and_the_mcap_becomes_a_linked_recording(
    client: TestClient, lab: str
) -> None:
    rid, _ = approved(client, recording_spec(client))
    assert all(t["capture_state"] == "pending" for t in trials_of(client, rid))
    assert work_all() == ["succeeded"] * 4 and capture() == 4
    ts = trials_of(client, rid)
    assert {t["capture_state"] for t in ts} == {"stored"}
    for t in ts:
        art = t["artifacts"][0]
        assert art["name"] == "recording" and art["state"] == "stored" and art["sha256"].startswith("sha256:")
        got = client.get(f"{ORG}/experiment-trials/{t['id']}/artifacts/recording", headers=VIC)
        assert got.status_code == 200 and "sha256:" + hashlib.sha256(got.content).hexdigest() == art["sha256"]
        assert got.headers["x-artifact-sha256"] == art["sha256"] and len(got.content) == art["size_bytes"]
        # the recording is linked to the workflow run, the model version and the host's identity, as reported
        rec = ok(client.get(f"{PROJECT}/twin/recordings/{t['recording_id']}", headers=VIC))
        assert rec["sha256"] == art["sha256"] and rec["model"].endswith("@1")
        assert rec["identity"]["seed"] == t["seed"] and rec["identity"]["kind"] == "selftest"
        link = rec["run"]
        assert link["id"] == t["run_id"] and link["arm"] == t["arm"] and link["seed"] == t["seed"]
        assert link["verdict"] == t["verdict"] and link["contract"] == "stop-on-command-loss"
        assert link["experiment"] == "stop" and link["version"] == 1 and rec["episode"] is None
        events = {e["kind"] for e in rec["events"]}
        # the twin's own rule over the recorded messages, next to (never replacing) the engine's verdict
        assert ("motion_continues" in events) == (t["arm"] == "pre-fix"), (t["arm"], events)
    # artifacts are for workspace members only
    make_org(client, "eve", "other")
    tid = ts[0]["id"]
    assert client.get(f"{ORG}/experiment-trials/{tid}/artifacts/recording", headers=as_user("eve")).status_code == 404
    assert client.get(f"{ORG}/experiment-trials/{tid}/artifacts/telemetry", headers=VIC).status_code == 404


def test_the_assistant_explains_a_trial_from_the_runs_own_verification_and_contract(
    client: TestClient,
    lab: str,
    api_url: str,  # noqa: F811
) -> None:
    import httpx

    rid, _ = approved(client, recording_spec(client, seeds=[3], repetitions=1))
    work_all()
    capture()
    bad = next(t for t in trials_of(client, rid) if t["arm"] == "pre-fix")
    good = next(t for t in trials_of(client, rid) if t["arm"] == "fix")
    rec = ok(client.get(f"{PROJECT}/twin/recordings/{bad['recording_id']}", headers=VIC))
    ev = next(e for e in rec["events"] if e["kind"] == "motion_continues")
    # through the real assistant endpoint, as the caller: the tool fetches the recording and the run itself
    r = httpx.post(
        f"{api_url}{ORG}/assistant/tools/explain_recording_event",
        json={"arguments": {"project": "robots", "recording_id": bad["recording_id"], "event_id": ev["id"]}},
        headers=VIC,
        timeout=60,
    ).json()
    assert r["is_error"] is False, r
    out = r["result"]
    judged = next(f for f in out["findings"] if "OpenMHS engine judged" in f["statement"])
    run = ok(client.get(f"{ORG}/workflow-runs/{bad['run_id']}", headers=VIC))
    assert "trial pre-fix, seed 3 of experiment Stop on command loss v1" in judged["statement"]
    assert "violated" in judged["statement"] and "stop-on-command-loss" in judged["statement"]
    assert f"verification:{run['id']}" in judged["evidence"] and f"workflow-run:{run['id']}" in judged["evidence"]
    assert any(e.startswith("contract:") for e in judged["evidence"])
    assert "Evidence class: simulated" in judged["statement"]
    assert any("agree" in f["statement"] or "point the same way" in f["statement"] for f in out["findings"])
    assert out["basis"].startswith("rule-based")
    assert not any("not linked" in n for n in out["not_known"])
    # the passing arm: the engine says satisfied and the twin raises no problem
    gr = ok(client.get(f"{PROJECT}/twin/recordings/{good['recording_id']}", headers=VIC))
    assert gr["run"]["verdict"] == "SATISFIED" and not [e for e in gr["events"] if e["severity"] == "problem"]


def test_a_trial_that_did_not_complete_says_so_and_stores_nothing(client: TestClient, lab: str) -> None:
    sc = scenario(client, "selftest-escape")
    spec = drive_spec(
        client,
        scenario={"id": "selftest-escape", "version": "1", "definition_sha256": sc["definition_sha256"]},
        initial_conditions={},
        seeds=[],
        repetitions=1,
        arms=[{"key": "bad", "parameters": {}}],
        observations={"measurements": ["sum"], "artifacts": ["telemetry"]},
        contract={
            "name": "sum",
            "version": "1",
            "conditions": [{"name": "sum", "measurement": "sum", "op": "eq", "value": 1}],
        },
    )
    rid, _ = approved(client, spec)
    assert work_all() == ["failed"] and capture() == 1
    t = trials_of(client, rid)[0]
    assert t["state"] == "failed" and t["capture_state"] == "none" and t["artifacts"] == []
    assert "failed" in t["capture_error"] and "nothing to capture" in t["capture_error"]


def test_bytes_the_host_will_not_vouch_for_are_not_stored(client: TestClient, lab: str, sim_host_work: Path) -> None:
    rid, _ = approved(client, recording_spec(client, seeds=[3], repetitions=1))
    work_all()
    # corrupt one trial's file on the host after its run: the host re-hashes before serving and refuses
    victim = next(t for t in trials_of(client, rid) if t["arm"] == "pre-fix")
    path = sim_host_work / "runs" / victim["host_run"]["run_id"] / "run" / "drive.mcap"
    path.write_bytes(path.read_bytes()[:-1] + b"X")
    assert capture() == 2
    by_arm = {t["arm"]: t for t in trials_of(client, rid)}
    assert by_arm["fix"]["capture_state"] == "stored" and by_arm["fix"]["recording_id"]
    bad = by_arm["pre-fix"]
    assert bad["capture_state"] == "failed" and bad["recording_id"] is None
    assert bad["artifacts"][0]["state"] == "rejected" and "storage_key" not in bad["artifacts"][0]
    assert "HTTP 409" in bad["capture_error"]
    assert client.get(f"{ORG}/experiment-trials/{bad['id']}/artifacts/recording", headers=VIC).status_code == 404


def test_the_platform_checks_the_digest_itself_when_a_host_serves_other_bytes() -> None:
    """A real HTTP server that reports one digest and serves other bytes: the second line of defence."""
    import http.server
    import threading

    from app.experiments.capture import CaptureError, _download
    from pap_device_sdk import WotHttpAdapter

    body = b"these are not the bytes that were hashed"

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: Any) -> None:
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        adapter = WotHttpAdapter(f"http://127.0.0.1:{srv.server_port}")
        entry = {"name": "recording", "sha256": hashlib.sha256(b"something else").hexdigest(), "size_bytes": len(body)}
        with pytest.raises(CaptureError, match="do not match what the host reported"):
            _download(adapter, "r1", entry, 1024)
        good = {**entry, "sha256": hashlib.sha256(body).hexdigest()}
        sp = _download(adapter, "r1", good, 1024)
        assert sp.sha256 == "sha256:" + hashlib.sha256(body).hexdigest() and sp.size == len(body)
        sp.close()
        with pytest.raises(CaptureError, match="above the limit"):
            _download(adapter, "r1", {**good, "size_bytes": 5000}, 1024)
    finally:
        srv.shutdown()


def test_only_the_artifacts_the_spec_lists_are_captured(client: TestClient, lab: str) -> None:
    sc = scenario(client, "selftest-sum")
    base = drive_spec(
        client,
        scenario={"id": "selftest-sum", "version": "1", "definition_sha256": sc["definition_sha256"]},
        initial_conditions={"b": 1},
        seeds=[],
        repetitions=1,
        arms=[{"key": "one", "parameters": {"a": 1, "rows": 3}}],
        contract={
            "name": "sum",
            "version": "1",
            "conditions": [{"name": "sum", "measurement": "sum", "op": "eq", "value": 2}],
        },
    )
    rid, _ = approved(client, {**base, "observations": {"measurements": ["sum"], "artifacts": []}})
    work_all()
    capture()
    t = trials_of(client, rid)[0]
    assert t["capture_state"] == "none" and t["artifacts"] == []  # the host left a telemetry file; nobody asked for it
    rid2, _ = approved(client, {**base, "observations": {"measurements": ["sum"], "artifacts": ["telemetry"]}})
    work_all()
    capture()
    t = trials_of(client, rid2)[0]
    assert t["capture_state"] == "stored" and [a["name"] for a in t["artifacts"]] == ["telemetry"]
    body = client.get(f"{ORG}/experiment-trials/{t['id']}/artifacts/telemetry", headers=VIC).text
    assert body.splitlines()[0] == "i,value" and len(body.splitlines()) == 4  # the bytes the scenario wrote


def test_a_recording_upload_is_processed_in_bounded_memory(client: TestClient, lab: str, monkeypatch: Any) -> None:
    """The 2026-11-22 gate raised MemoryError reading an upload: read(limit + 1) reserves that many bytes up front,
    so every recording upload, even a small one, asked the allocator for 96 MiB. Peak traced memory must now stay far
    below the 96 MiB limit for a real recording, and an oversize upload is refused after reading only a little."""
    import tracemalloc

    from test_twin_recordings import FIX, run_files

    ok(client.post(f"{ORG}/projects", json={"slug": "arm", "name": "Arm"}, headers=ADA), 201)
    mcap, summary, identity, _ = run_files(FIX)
    tracemalloc.start()
    r = client.post(
        f"{ORG}/projects/arm/twin/recordings",
        data={"label": "bounded", "summary": json.dumps(summary), "identity": json.dumps(identity)},
        files={"file": ("bounded.mcap", mcap, "application/octet-stream")},
        headers=ADA,
    )
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert r.status_code == 201, r.text
    assert peak < 24 * 1024 * 1024, f"peak {peak / 2**20:.1f} MiB for a {len(mcap) / 2**20:.1f} MiB recording"

    import app.twin.routes as routes

    monkeypatch.setattr(routes, "MAX_RECORDING_BYTES", 5 * 1024 * 1024)
    big = b"\x89MCAP0\r\n" + b"\0" * (6 * 1024 * 1024)
    tracemalloc.start()
    r = client.post(
        f"{ORG}/projects/arm/twin/recordings",
        data={"label": "too big"},
        files={"file": ("big.mcap", big, "application/octet-stream")},
        headers=ADA,
    )
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert r.status_code == 413 and r.json()["detail"]["code"] == "twin.too_large"
    assert peak < 24 * 1024 * 1024
    assert len(ok(client.get(f"{ORG}/projects/arm/twin/recordings", headers=ADA))) == 1  # nothing was stored for it


# ------------------------------------------------------------------------- camera-comparison infrastructure check


def test_a_configuration_comparison_has_what_a_camera_comparison_needs(client: TestClient, lab: str) -> None:
    """The infrastructure a camera-configuration comparison will use, checked without building a camera scenario: three
    configuration arms of one pinned scenario, the same fixed conditions in every trial, one workflow and one captured
    recording per trial, results grouped per arm. (The configurations here are speeds of the self-test base; a camera
    scenario would vary a camera profile parameter and output visibility measurements instead.)"""
    spec = recording_spec(
        client,
        seeds=[],
        repetitions=2,
        initial_conditions={"drive_s": 1.0, "stop_on_command_loss": True},
        arms=[
            {"key": "profile-a", "title": "Profile A", "role": "baseline", "parameters": {"speed_mps": 0.2}},
            {"key": "profile-b", "title": "Profile B", "parameters": {"speed_mps": 0.4}},
            {"key": "profile-c", "title": "Profile C", "parameters": {"speed_mps": 0.6}},
        ],
        limits={"max_trials": 6, "max_wall_time_s": 600},
    )
    rid, _ = approved(client, spec)
    assert work_all() == ["succeeded"] * 6 and capture() == 6
    wfs = [w for w in ok(client.get(f"{ORG}/workflows", headers=VIC)) if w["template"] == "experiment"]
    assert len(wfs) == 3  # one workflow per configuration (no seeds: repetitions are runs of the same workflow)
    inputs = {w["parameters"]["arm"]: w["definition"]["steps"][0]["input"]["parameters"] for w in wfs}
    for arm, p in inputs.items():  # the fixed conditions are identical in every arm; only the configuration differs
        assert {k: v for k, v in p.items() if k != "speed_mps"} == {"drive_s": 1.0, "stop_on_command_loss": True}, arm
    assert sorted(p["speed_mps"] for p in inputs.values()) == [0.2, 0.4, 0.6]
    d = ok(client.get(f"{ORG}/experiment-requests/{rid}", headers=VIC))
    assert [a["arm"] for a in d["arms"]] == ["profile-a", "profile-b", "profile-c"]
    assert all(a["trials"] == 2 and len(a["values"]["travel_after_kill_m"]) == 2 for a in d["arms"])
    recs = {t["recording_id"] for t in d["trial_results"]}
    assert None not in recs and len({t["artifacts"][0]["sha256"] for t in d["trial_results"]}) >= 3
    # Each trial's recording is its own run's, linked to that run and arm in the twin.
    for t in d["trial_results"]:
        rec = ok(client.get(f"{PROJECT}/twin/recordings/{t['recording_id']}", headers=VIC))
        assert rec["run"]["arm"] in {"profile-a", "profile-b", "profile-c"}


# ---------------------------------------------------------------------- SIM-007: setups judged as releases


def test_two_setups_are_judged_as_releases_by_the_engine_over_every_finished_trial(
    client: TestClient, lab: str
) -> None:
    """From contract violations to a release verdict: the trials of every approved run of a version accumulate into two
    evidence files, the setups become releases, and an ordinary evaluation job gives the engine's comparison."""
    from test_jobs import work_once as evaluate_once

    ok(client.post(f"{ORG}/projects", json={"slug": "robots", "name": "Robots"}, headers=ADA), 201)
    rid1, v = approved(client, drive_spec(client))
    rid2 = request(client)["id"]  # the same version again: evidence accumulates
    decide(client, rid2, "approve", v["spec_sha256"])
    assert work_all() == ["succeeded"] * 8
    trials = trials_of(client, rid1) + trials_of(client, rid2)

    url = f"{ORG}/experiments/stop/release-evaluations"
    body = {"version": 1, "baseline_arm": "pre-fix", "candidate_arm": "fix", "project": "robots"}
    assert client.post(url, json=body, headers=VIC).status_code == 403
    bad = client.post(url, json={**body, "candidate_arm": "pre-fix"}, headers=ADA)
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "experiment.arms"
    ev = ok(client.post(url, json=body, headers=ADA), 201)
    assert ev["trials"] == {"baseline": 4, "candidate": 4} and ev["state"] == "queued" and ev["verdict"] is None

    # The evidence files hold exactly the trials' own measurements, one row per trial, nothing derived.
    arts = {a["filename"]: a for a in ok(client.get(f"{ORG}/projects/robots/artifacts", headers=ADA))}
    import csv as _csv
    import io as _io

    for arm, fname in (("pre-fix", "stop-v1-pre-fix.csv"), ("fix", "stop-v1-fix.csv")):
        from app.db import session_factory
        from app.evidence.models import Artifact
        from app.evidence.storage import get_storage

        with session_factory()() as s:
            a = s.get(Artifact, uuid.UUID(arts[fname]["id"]))
            assert a is not None
            rows = list(_csv.DictReader(_io.StringIO(get_storage().get(a.storage_key).decode())))
        mine = {t["run_id"]: t for t in trials if t["arm"] == arm}
        assert {r["episode_id"] for r in rows} == set(mine)
        for r in rows:
            assert float(r["travel_after_kill_m"]) == mine[r["episode_id"]]["measurements"]["travel_after_kill_m"]
    rels = {r["label"]: r for r in ok(client.get(f"{ORG}/projects/robots/releases", headers=VIC))}
    assert {"stop-v1-pre-fix", "stop-v1-fix"} <= set(rels)

    assert evaluate_once() == "succeeded"  # the evaluation worker with the pinned engine, as for uploaded evidence
    ev = ok(client.get(url, headers=VIC))[0]
    assert ev["state"] == "succeeded" and ev["verdict"]["basis"] == "compare_verified"
    verdict, reasons = ev["verdict"]["verdict"], " ".join(ev["verdict"]["reasons"])
    # The engine's own rule: fewer known outcomes per arm than its min_known (default 30) is insufficient evidence.
    assert verdict == "insufficient_evidence" and "fewer than 30" in reasons, ev["verdict"]
    # Judging the same trials again is the same evaluation (the job is content-addressed by its inputs).
    again = ok(client.post(url, json=body, headers=ADA), 200)
    assert again["id"] == ev["id"] and len(ok(client.get(url, headers=VIC))) == 1
    make_org(client, "eve", "other")
    assert client.get(url, headers=as_user("eve")).status_code == 404
