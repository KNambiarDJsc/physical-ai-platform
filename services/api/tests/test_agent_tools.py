"""AGT-001: typed read-only tools over MCP/stdio against the REAL API (uvicorn in a thread), the REAL virtual lab and
the REAL engine. Roles do the enforcing: the tools run as a viewer, who can read and propose but not approve."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient
from helpers import add_member, as_user, make_org, ok
from test_workflows import lab_call, work_once

pytestmark = pytest.mark.engine
ORG = "/api/v1/orgs/lab"
ADA = as_user("ada")


class Mcp:
    """A real MCP client over a subprocess's stdio."""

    def __init__(self, url: str, token: str) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "pap_agent_tools"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={**os.environ, "PAP_API_URL": url, "PAP_API_TOKEN": token},
        )
        self.q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.n = 0
        init = self.rpc(
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
        )
        assert init["result"]["serverInfo"]["name"] == "pap-agent-tools"
        self.notify("notifications/initialized")

    def _pump(self) -> None:
        assert self.proc.stdout
        for line in self.proc.stdout:
            self.q.put(line)

    def send(self, msg: dict[str, Any]) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def notify(self, method: str) -> None:
        self.send({"jsonrpc": "2.0", "method": method})

    def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.n += 1
        self.send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        reply = json.loads(self.q.get(timeout=60))
        assert reply["id"] == self.n
        return reply  # type: ignore[no-any-return]

    def tool(self, name: str, **args: Any) -> dict[str, Any]:
        return self.rpc("tools/call", {"name": name, "arguments": args})["result"]  # type: ignore[no-any-return]

    def data(self, name: str, **args: Any) -> Any:
        r = self.tool(name, **args)
        assert not r["isError"], r["content"][0]["text"]
        return json.loads(r["content"][0]["text"])

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


@pytest.fixture
def api_url(client: TestClient) -> Iterator[str]:
    import socket

    from app.main import create_app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


@pytest.fixture
def world(client: TestClient, with_lab: str, omhs: Any, api_url: str) -> dict[str, Any]:
    make_org(client, "ada", "lab")
    add_member(client, "ada", "lab", "vic", "viewer")
    add_member(client, "ada", "lab", "eve", "engineer")
    for key in ("virtual-lab", "plant-floor"):
        ok(client.post(f"{ORG}/environments", json={"config_key": key}, headers=ADA), 201)
        ok(client.post(f"{ORG}/environments/{key}/discover", headers=ADA))
    lab_call(with_lab, "simulation", "reset")
    body = {
        "slug": "dispense",
        "name": "Dispense 100 µL",
        "environment": "virtual-lab",
        "template": "dispense-and-verify",
        "parameters": {"volume_ul": 100},
    }
    ok(client.post(f"{ORG}/workflows", json=body, headers=ADA), 201)
    ok(client.post(f"{ORG}/workflows", json={**body, "slug": "floor", "environment": "plant-floor"}, headers=ADA), 201)
    return {"lab": with_lab, "url": api_url}


@pytest.fixture
def viewer(world: dict[str, Any]) -> Iterator[Mcp]:
    m = Mcp(world["url"], "dev:vic")
    yield m
    m.close()


def contradiction_run(client: TestClient, lab: str) -> dict[str, Any]:
    lab_call(lab, "simulation", "set_fault", {"fault": "partial_blockage"})
    try:
        r = ok(client.post(f"{ORG}/workflows/dispense/runs", headers=ADA), 201)
        assert work_once() == "succeeded"
    finally:
        lab_call(lab, "simulation", "reset")
    return ok(client.get(f"{ORG}/workflow-runs/{r['id']}", headers=ADA))  # type: ignore[no-any-return]


def test_the_tool_list_is_exactly_the_allowlist_with_typed_schemas_and_honest_hints(viewer: Mcp) -> None:
    from pap_agent_tools.tools import ALLOWLIST

    tools = viewer.rpc("tools/list")["result"]["tools"]
    assert {t["name"] for t in tools} == ALLOWLIST and len(tools) == 13
    for t in tools:
        assert t["inputSchema"]["type"] == "object" and t["inputSchema"]["properties"] is not None, t["name"]
        assert t["description"]
        assert t["annotations"]["readOnlyHint"] is (t["name"] != "propose_experiment"), t["name"]
        assert t["annotations"]["destructiveHint"] is False
        assert not re.search(r"approve|reject|start|create|command|execute|reset|fault|delete|dispatch", t["name"]), t[
            "name"
        ]
    assert "org" in next(t for t in tools if t["name"] == "list_devices")["inputSchema"]["required"]
    prop = next(t for t in tools if t["name"] == "propose_experiment")["inputSchema"]
    assert (
        set(prop["required"]) == {"org", "workflow", "rationale"} and prop["properties"]["rationale"]["minLength"] == 10
    )


def test_a_contradiction_is_investigated_with_findings_that_cite_stored_evidence(
    client: TestClient, world: dict[str, Any], viewer: Mcp
) -> None:
    run = contradiction_run(client, world["lab"])
    assert run["outcome_class"] == "contradiction"
    ws = viewer.data("list_workspaces")
    assert ws == [{"slug": "lab", "role": "viewer"}]
    inv = viewer.data("investigate_run", org="lab", run_id=run["id"])
    assert inv["method"].startswith("rule-based") and inv["state"] == "succeeded"
    top = inv["findings"][0]
    assert top["severity"] == "bad" and "reported succeeded" in top["statement"] and "observed" in top["statement"]
    # every cited id exists in the stored run
    contract = run["provenance"]["contract_sha256"][:12]
    assert set(top["evidence"]) == {f"run:{run['id']}", f"verification:{run['id']}", f"contract:{contract}"}
    mass = run["verification"]["evidence"][1]["value"]["value"]
    assert str(mass) in top["statement"]
    sug = inv["suggested_experiments"]
    assert [s["workflow"] for s in sug] == ["dispense"] and f"run:{run['id']}" in sug[0]["rationale"]
    # a suggestion is not a proposal
    assert ok(client.get(f"{ORG}/experiment-proposals", headers=ADA)) == []
    # reads go through the platform as the caller
    full = viewer.data("get_workflow_run", org="lab", run_id=run["id"])
    assert full["verdict"] == "VIOLATED" and full["reported"]["value"] == "succeeded"
    devices = {d["key"]: d for d in viewer.data("list_devices", org="lab") if d["environment"] == "virtual-lab"}
    assert devices["balance"]["actions"] == ["tare", "weigh"] and "mass_g" in devices["balance"]["properties"]
    live = viewer.data("read_observation", org="lab", device_id=devices["balance"]["id"], property="readability_g")
    assert live["value"] == 0.0001


def test_a_viewer_can_propose_but_never_approve_and_an_engineer_approval_runs_through_the_executor(
    client: TestClient, world: dict[str, Any], viewer: Mcp
) -> None:
    runs_before = len(ok(client.get(f"{ORG}/workflow-runs", headers=ADA)))
    p = viewer.data(
        "propose_experiment",
        org="lab",
        workflow="dispense",
        rationale="Repeat to check the contradiction.",
        evidence_ids=["run:abc"],
    )
    assert p["state"] == "proposed" and p["channel"] == "agent-tools" and p["run_id"] is None and p["proposed_by"]
    assert len(ok(client.get(f"{ORG}/workflow-runs", headers=ADA))) == runs_before  # nothing was queued, let alone run
    # the platform, not the tool layer, refuses the viewer
    pid = p["id"]
    for verb in ("approve", "reject"):
        r = client.post(f"{ORG}/experiment-proposals/{pid}/{verb}", json={}, headers=as_user("vic"))
        assert r.status_code == 403, (verb, r.status_code)
    assert viewer.data("list_experiment_proposals", org="lab", state="proposed")[0]["id"] == pid
    # an engineer approves: only then is a run queued, and the executor runs it as any other
    a = ok(client.post(f"{ORG}/experiment-proposals/{pid}/approve", headers=as_user("eve")))
    assert a["state"] == "approved" and a["decided_by"] and a["run_id"]
    assert ok(client.get(f"{ORG}/workflow-runs/{a['run_id']}", headers=ADA))["state"] == "queued"
    assert work_once() == "succeeded"
    assert ok(client.get(f"{ORG}/workflow-runs/{a['run_id']}", headers=ADA))["verdict"] == "SATISFIED"
    assert (
        client.post(f"{ORG}/experiment-proposals/{pid}/approve", headers=as_user("eve")).status_code == 409
    )  # decided once


def test_a_proposal_in_a_physical_environment_cannot_be_approved(
    client: TestClient, world: dict[str, Any], viewer: Mcp
) -> None:
    p = viewer.data("propose_experiment", org="lab", workflow="floor", rationale="Try it on the plant floor.")
    r = client.post(f"{ORG}/experiment-proposals/{p['id']}/approve", headers=as_user("eve"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_simulated"
    assert ok(client.get(f"{ORG}/workflow-runs", headers=ADA)) == []  # no run was queued
    rej = ok(
        client.post(f"{ORG}/experiment-proposals/{p['id']}/reject", json={"note": "physical"}, headers=as_user("eve"))
    )
    assert rej["state"] == "rejected" and rej["decision_note"] == "physical" and rej["run_id"] is None


def test_the_tools_cannot_reach_another_workspace(client: TestClient, world: dict[str, Any], viewer: Mcp) -> None:
    run = contradiction_run(client, world["lab"])
    make_org(client, "mallory", "other")
    outsider = Mcp(world["url"], "dev:mallory")
    try:
        assert outsider.data("list_workspaces") == [{"slug": "other", "role": "admin"}]
        for name, args in (
            ("get_workflow_run", {"org": "lab", "run_id": run["id"]}),
            ("list_devices", {"org": "lab"}),
            ("investigate_run", {"org": "lab", "run_id": run["id"]}),
        ):
            r = outsider.tool(name, **args)
            assert r["isError"] and "HTTP 404" in r["content"][0]["text"], name
            assert run["id"] not in r["content"][0]["text"] or "refused" in r["content"][0]["text"]
        r = outsider.tool("propose_experiment", org="lab", workflow="dispense", rationale="not allowed at all")
        assert r["isError"] and "HTTP 404" in r["content"][0]["text"]
    finally:
        outsider.close()
    assert ok(client.get(f"{ORG}/experiment-proposals", headers=ADA)) == []


def test_bad_input_unknown_tools_and_methods_are_answered_not_crashed(viewer: Mcp) -> None:
    r = viewer.tool("get_workflow_run", org="lab", run_id="not-a-uuid")
    assert r["isError"] and "invalid input" in r["content"][0]["text"] and "run_id" in r["content"][0]["text"]
    r = viewer.tool("propose_experiment", org="lab", workflow="dispense", rationale="short")
    assert r["isError"] and "rationale" in r["content"][0]["text"]
    assert viewer.tool("approve_proposal", org="lab")["isError"]
    assert viewer.rpc("resources/list")["error"]["code"] == -32601
    assert viewer.rpc("ping")["result"] == {}
    assert viewer.tool("list_workspaces")["isError"] is False  # still serving


def test_no_credential_is_refused_at_start() -> None:
    p = subprocess.run(
        [sys.executable, "-m", "pap_agent_tools"],
        input="",
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "PAP_API_TOKEN"},
        timeout=30,
        check=False,
    )
    assert p.returncode != 0 and "PAP_API_TOKEN" in p.stderr
