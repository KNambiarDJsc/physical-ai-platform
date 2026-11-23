"""WF-001: durable simulated workflow runs, verified by the real pinned engine, against the real virtual laboratory.

Nothing here is mocked: the instruments are LabThings Things in a subprocess, the verdict is `openmhs outcome verify`,
and one test kills a real worker process mid-run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import add_member, as_user, make_org, ok

API = Path(__file__).resolve().parents[1]
ORG = "/api/v1/orgs/lab"
H = as_user("ada")
pytestmark = pytest.mark.engine


def work_once() -> str | None:
    """One claim + execute of a workflow run, exactly as the worker process does."""
    from app.config import get_settings
    from app.db import session_factory
    from app.workflows import service
    from app.workflows.executor import execute_run

    with session_factory()() as s:
        run_id = service.claim(s, "test-worker", get_settings().worker_lease_s)
    return execute_run(run_id, "test-worker") if run_id else None


def lab_call(url: str, thing: str, action: str, payload: dict[str, Any] | None = None) -> Any:
    from pap_device_sdk import WotHttpAdapter

    inv = WotHttpAdapter(url).invoke_action(thing, action, payload or {})
    assert inv.status == "completed", inv
    return inv.output


def invocations(url: str, action: str) -> int:
    return sum(1 for i in httpx.get(f"{url}/action_invocations", timeout=10).json() if i["action"] == action)


@pytest.fixture
def lab(client: TestClient, with_lab: str, omhs: Any) -> str:
    make_org(client, "ada", "lab")
    for key in ("virtual-lab", "plant-floor"):
        ok(client.post(f"{ORG}/environments", json={"config_key": key}, headers=H), 201)
        ok(client.post(f"{ORG}/environments/{key}/discover", headers=H))
    lab_call(with_lab, "simulation", "reset")
    return with_lab


def workflow(client: TestClient, slug: str = "dispense", env: str = "virtual-lab", **params: Any) -> dict[str, Any]:
    body = {"slug": slug, "name": slug, "environment": env, "template": "dispense-and-verify", "parameters": params}
    return ok(client.post(f"{ORG}/workflows", json=body, headers=H), 201)


def run(client: TestClient, slug: str = "dispense") -> dict[str, Any]:
    return ok(client.post(f"{ORG}/workflows/{slug}/runs", headers=H), 201)


def get_run(client: TestClient, run_id: str) -> dict[str, Any]:
    return ok(client.get(f"{ORG}/workflow-runs/{run_id}", headers=H))


def test_a_healthy_dispense_is_verified_by_the_engine(client: TestClient, lab: str) -> None:
    import json

    workflow(client, volume_ul=50, tolerance_pct=2)
    r = run(client)
    # The API only queued it: nothing has been sent to any device.
    assert r["state"] == "queued" and {s["state"] for s in r["steps"]} == {"pending"}
    assert work_once() == "succeeded"
    r = get_run(client, r["id"])
    assert r["state"] == "succeeded" and [s["state"] for s in r["steps"]] == ["completed"] * 3
    assert r["reported"]["value"] == "succeeded" and r["reported"]["output"]["reported_dispensed_ul"] == 50
    assert r["verdict"] == "SATISFIED" and r["outcome_class"] == "supported_success"
    cond = r["verification"]["report"]["conditions"][0]
    assert cond["result"] == "TRUE" and cond["evidence"] == "delivered_mass" and cond["observed"]
    lock = json.loads((API.parents[1] / "engine.lock.json").read_text(encoding="utf-8"))
    assert r["provenance"]["engine"]["commit"].startswith(lock["commit"][:7])
    assert r["provenance"]["evidence_class"] == "simulated" and len(r["provenance"]["contract_sha256"]) == 64
    assert r["steps"][1]["idempotent"] and not r["steps"][0]["idempotent"]


def test_a_blocked_line_is_a_contradiction_reported_success_verified_violated(client: TestClient, lab: str) -> None:
    workflow(client, volume_ul=100)
    lab_call(lab, "simulation", "set_fault", {"fault": "partial_blockage"})
    try:
        r = run(client)
        assert work_once() == "succeeded"
    finally:
        lab_call(lab, "simulation", "reset")
    r = get_run(client, r["id"])
    assert r["reported"]["value"] == "succeeded"  # the pump says it dispensed 100 µL
    assert r["verdict"] == "VIOLATED" and r["outcome_class"] == "contradiction"  # the balance says otherwise
    observed = r["verification"]["evidence"][1]["value"]["value"]
    assert 0.055 < observed < 0.070


def test_no_command_is_sent_to_an_environment_configured_physical(client: TestClient, lab: str) -> None:
    workflow(client, slug="on-the-floor", env="plant-floor")
    before = invocations(lab, "tare")
    r = run(client, "on-the-floor")
    assert work_once() == "failed"
    r = get_run(client, r["id"])
    assert r["error"]["code"] == "safety.not_simulated"
    assert r["steps"][0]["state"] == "refused" and r["steps"][0]["dispatches"] == 0
    assert {s["state"] for s in r["steps"][1:]} == {"pending"}
    assert invocations(lab, "tare") == before  # nothing reached the instrument


def _crash(run_id: str, *, done: int, in_flight: int) -> None:
    """Leave the run as a worker that died mid-step would: steps < done completed, step `in_flight` dispatching,
    the lease expired. Then let recovery re-queue it."""
    from app.db import session_factory, utcnow
    from app.workflows import service
    from app.workflows.models import WorkflowRun, WorkflowStep
    from sqlalchemy import select

    with session_factory()() as s:
        r = s.get(WorkflowRun, uuid.UUID(run_id))
        assert r is not None
        r.state, r.attempts, r.lease_owner = "running", 1, "dead-worker"
        r.lease_expires_at = utcnow() - timedelta(seconds=5)
        for st in s.scalars(select(WorkflowStep).where(WorkflowStep.run_id == r.id)):
            if st.position < done:
                st.state = "completed"
            elif st.position == in_flight:
                st.state, st.dispatches = "dispatching", 1
        s.commit()
        assert service.recover_expired(s) == 1


def test_a_non_idempotent_step_in_flight_is_not_sent_again(client: TestClient, lab: str) -> None:
    workflow(client)
    r = run(client)
    _crash(r["id"], done=0, in_flight=0)  # died while the tare (no request id) was in flight
    before = invocations(lab, "tare")
    assert work_once() == "outcome_unknown"
    r = get_run(client, r["id"])
    assert r["state"] == "outcome_unknown" and r["error"]["code"] == "step.outcome_unknown"
    assert r["steps"][0]["state"] == "outcome_unknown" and r["steps"][0]["dispatches"] == 1
    assert invocations(lab, "tare") == before


def test_an_idempotent_step_in_flight_is_resent_and_takes_effect_once(client: TestClient, lab: str) -> None:
    workflow(client, volume_ul=200)
    r = run(client)
    # The dead worker had tared and its dispense command had reached the pump before it died.
    lab_call(lab, "balance", "tare")
    lab_call(lab, "pump", "dispense", {"volume_ul": 200, "request_id": r["steps"][1]["request_id"]})
    _crash(r["id"], done=1, in_flight=1)
    assert work_once() == "succeeded"
    r = get_run(client, r["id"])
    assert r["steps"][1]["dispatches"] == 2 and r["steps"][1]["output"]["repeated"] == "true"
    assert r["verdict"] == "SATISFIED"  # one dispense of 200 µL on the balance, not two
    mass = r["verification"]["evidence"][1]["value"]["value"]
    assert 0.195 < mass < 0.204


def test_a_killed_worker_process_is_replaced_and_every_dispense_happens_once(
    client: TestClient, lab: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings
    from app.db import session_factory
    from app.workers.run import run as worker_loop
    from app.workflows.models import WorkflowStep
    from sqlalchemy import select

    monkeypatch.setenv("PAP_WORKER_LEASE_S", "5")
    get_settings.cache_clear()
    n, vol = 8, 20.0
    target = n * vol * 0.0009982
    definition = {
        "schema": "pap.workflow/1",
        "steps": [{"id": "tare", "device": "balance", "action": "tare"}]
        + [{"id": f"d{i}", "device": "pump", "action": "dispense", "input": {"volume_ul": vol}} for i in range(n)]
        + [{"id": "weigh", "device": "balance", "action": "weigh"}],
        "verification": {
            "contract": "volume-delivered", "version": "1", "claim_step": f"d{n - 1}",
            "evidence": [{"name": "delivered_mass", "step": "weigh", "output_field": "mass_g",
                          "signal": "vessel.net_mass", "unit": "g"}],
            "conditions": [{"name": "eight doses of 20 µL, ± 2 %", "evidence": "delivered_mass", "op": "between",
                            "min": {"value": target * 0.98, "unit": "g"},
                            "max": {"value": target * 1.02, "unit": "g"}}],
        },
    }  # fmt: skip
    ok(client.post(f"{ORG}/workflows", json={"slug": "doses", "name": "doses", "environment": "virtual-lab",
                                             "definition": definition}, headers=H), 201)  # fmt: skip
    r = run(client, "doses")

    def completed() -> int:
        with session_factory()() as s:
            q = select(WorkflowStep).where(WorkflowStep.run_id == uuid.UUID(r["id"]), WorkflowStep.state == "completed")
            return len(list(s.scalars(q)))

    proc = subprocess.Popen(
        [sys.executable, "-m", "app.workers.run", "--once"], cwd=API, env={**os.environ, "PYTHONPATH": str(API)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        deadline = time.monotonic() + 90
        while completed() < 3:  # tare and two doses done: kill it in the middle of the run
            assert proc.poll() is None, "worker exited early"
            assert time.monotonic() < deadline, "worker made no progress"
            time.sleep(0.05)
    finally:
        proc.kill()  # hard kill: no cleanup handlers run
        proc.wait()
    assert 3 <= completed() < n + 2
    time.sleep(get_settings().worker_lease_s + 1)
    worker_loop(once=True, poll_s=0.2)
    r = get_run(client, r["id"])
    assert r["state"] == "succeeded" and r["attempts"] == 2
    assert all(s["state"] == "completed" for s in r["steps"])
    mass = r["verification"]["evidence"][1]["value"]["value"]
    assert target * 0.98 < mass < target * 1.02  # a repeated dose would add 12.5 %
    assert r["verdict"] == "SATISFIED"


def test_definitions_are_checked_against_the_discovered_devices_and_roles(client: TestClient, lab: str) -> None:
    def bad(definition: dict[str, Any]) -> str:
        body = {"slug": "bad", "name": "bad", "environment": "virtual-lab", "definition": definition}
        r = client.post(f"{ORG}/workflows", json=body, headers=H)
        assert r.status_code == 422, r.text
        return str(r.json()["detail"]["code"])

    step = {"id": "a", "device": "pump", "action": "dispense", "input": {"volume_ul": 5}}
    assert bad({"steps": [dict(step, device="centrifuge")]}) == "workflow.unknown_device"
    assert bad({"steps": [dict(step, action="explode")]}) == "workflow.unknown_action"
    assert bad({"steps": [dict(step, input={})]}) == "workflow.missing_input"
    assert bad({"steps": [step, step]}) == "workflow.invalid"
    add_member(client, "ada", "lab", "vic", "viewer")
    workflow(client)
    assert client.post(f"{ORG}/workflows/dispense/runs", headers=as_user("vic")).status_code == 403
    assert len(ok(client.get(f"{ORG}/workflow-runs", headers=as_user("vic")))) == 0


def test_a_fault_is_a_visible_step_of_the_workflow_and_the_bench_is_left_healthy(client: TestClient, lab: str) -> None:
    """The failing demo case: the fault is injected and cleared by journaled steps, nothing is edited afterwards."""
    body = {
        "slug": "faulty", "name": "faulty", "environment": "virtual-lab", "template": "dispense-with-fault",
        "parameters": {"volume_ul": 50, "tolerance_pct": 2, "fault": "partial_blockage"},
    }  # fmt: skip
    ok(client.post(f"{ORG}/workflows", json=body, headers=H), 201)
    queued = run(client, "faulty")
    assert work_once() == "succeeded"
    r = get_run(client, queued["id"])
    assert [(s["device"], s["action"]) for s in r["steps"]] == [
        ("simulation", "set_fault"), ("balance", "tare"), ("pump", "dispense"), ("balance", "weigh"),
        ("simulation", "set_fault"),
    ]  # fmt: skip
    assert {s["state"] for s in r["steps"]} == {"completed"}
    assert r["reported"]["value"] == "succeeded" and r["reported"]["output"]["reported_dispensed_ul"] == 50
    assert r["verdict"] == "VIOLATED" and r["outcome_class"] == "contradiction"
    assert r["provenance"]["evidence_class"] == "simulated"
    observed = r["verification"]["evidence"][1]["value"]["value"]
    assert 0.028 < observed < 0.034  # about 62 % of the 0.0499 g that 50 µL of water weighs
    # the bench was cleared by the workflow's own last step: the next ordinary dispense is healthy
    workflow(client, "healthy", volume_ul=50, tolerance_pct=2)
    healthy = run(client, "healthy")
    assert work_once() == "succeeded"
    assert get_run(client, healthy["id"])["verdict"] == "SATISFIED"


def test_a_run_report_is_reproducible_labelled_escaped_and_private(client: TestClient, lab: str) -> None:
    import json

    workflow(client, "healthy", volume_ul=50, tolerance_pct=2)
    queued = run(client, "healthy")
    assert work_once() == "succeeded"
    rid = queued["id"]
    # a follow-up that cites the run, with markup in its rationale, must be shown as text
    prop = {
        "workflow": "healthy",
        "rationale": "Repeat <script>alert(1)</script> once.",
        "evidence_ids": [f"run:{rid}"],
    }
    pid = ok(client.post(f"{ORG}/experiment-proposals", json=prop, headers=as_user("ada")), 201)["id"]

    first = client.get(f"{ORG}/workflow-runs/{rid}/report.json", headers=H)
    second = client.get(f"{ORG}/workflow-runs/{rid}/report.json", headers=H)
    assert first.status_code == 200 and first.content == second.content  # same run, same bytes
    assert "attachment" in first.headers["content-disposition"]
    rep = json.loads(first.text)
    assert rep["schema"] == "pap.lab-run-report/1" and rep["evidence_class"] == "simulated"
    assert rep["independently_verified"]["verdict"] == "SATISFIED"
    assert rep["reported_by_instrument"]["value"] == "succeeded"
    assert len(rep["procedure"]["definition_sha256"]) == 64 and len(rep["execution"]) == 3
    assert [p["id"] for p in rep["follow_up_proposals"]] == [pid]
    assert rep["provenance"]["engine"]["commit"] and rep["provenance"]["contract_sha256"]

    page = client.get(f"{ORG}/workflow-runs/{rid}/report.html", headers=H)
    assert page.status_code == 200 and "SIMULATED EVIDENCE" in page.text and "SATISFIED" in page.text
    assert "<script>alert(1)" not in page.text and "&lt;script&gt;alert(1)" in page.text
    assert "default-src 'none'" in page.headers["content-security-policy"]

    make_org(client, "mallory", "other")
    for kind in ("json", "html"):
        r = client.get(f"/api/v1/orgs/other/workflow-runs/{rid}/report.{kind}", headers=as_user("mallory"))
        assert r.status_code == 404
        assert client.get(f"{ORG}/workflow-runs/{rid}/report.{kind}", headers=as_user("mallory")).status_code == 404
        assert client.get(f"{ORG}/workflow-runs/{rid}/report.{kind}").status_code == 401
