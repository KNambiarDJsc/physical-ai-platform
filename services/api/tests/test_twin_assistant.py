"""TWN-004: the engineering assistant in the twin runs the existing typed tools, as the caller, and explains an event
of a recording by citing stored evidence. Real API (uvicorn), real worker and engine, the two real recordings."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import as_user, make_org, ok
from test_agent_tools import Mcp, api_url  # noqa: F401  (api_url is a fixture)
from test_twin_recordings import FIX, MAIN, evaluate, upload

ORG = "/api/v1/orgs/lab"
P = f"{ORG}/projects/arm"
VERA = as_user("vera")


def ask(
    url: str, tool: str, arguments: dict[str, Any], headers: dict[str, str] = VERA, org: str = "lab"
) -> httpx.Response:
    return httpx.post(
        f"{url}/api/v1/orgs/{org}/assistant/tools/{tool}", json={"arguments": arguments}, headers=headers, timeout=60
    )


@pytest.fixture
def twin(client: TestClient, omhs: Any, api_url: str) -> dict[str, Any]:  # noqa: F811
    job, eps, _ = evaluate(client)
    rec = {}
    for run in (MAIN, FIX):
        r = upload(client, run, run, episode_id=eps[run]["id"])
        assert r.status_code == 201, r.text
        rec[run] = r.json()["id"]
    return {"url": api_url, "job": job, "eps": eps, "rec": rec}


def events(client: TestClient, rid: str) -> dict[str, dict[str, Any]]:
    d = ok(client.get(f"{P}/twin/recordings/{rid}", headers=VERA))
    return {e["kind"]: e for e in d["events"]}


@pytest.mark.engine
def test_the_assistant_can_only_reach_read_only_tools_as_the_caller(client: TestClient, twin: dict[str, Any]) -> None:
    url = twin["url"]
    from pap_agent_tools.tools import READ_ONLY

    listed = httpx.get(f"{url}{ORG}/assistant/tools", headers=VERA, timeout=30)
    assert listed.status_code == 200
    names = {t["name"] for t in listed.json()}
    assert names == set(READ_ONLY) and {"list_recordings", "get_recording", "explain_recording_event"} <= names
    assert all(t["input_schema"]["type"] == "object" for t in listed.json())
    for forbidden in ("propose_experiment", "approve_proposal", "start_run", "no_such_tool"):
        assert ask(url, forbidden, {"workflow": "x"}).status_code == 404, forbidden
    # it is the caller's own credential: none, or one with no access to this workspace, gets nothing
    assert (
        httpx.post(f"{url}{ORG}/assistant/tools/list_workspaces", json={"arguments": {}}, timeout=30).status_code == 401
    )
    make_org(client, "mallory", "evil", "other")
    assert ask(url, "list_recordings", {"project": "arm"}, as_user("mallory")).status_code == 404
    # a call may only name the workspace it is made in
    assert ask(url, "list_recordings", {"org": "evil", "project": "arm"}).status_code == 422
    # inside its own workspace a tool still goes through the API's checks: an unknown project is refused, as text
    refused = ask(url, "list_recordings", {"project": "nope"}).json()
    assert refused["is_error"] is True and "refused" in refused["result"] and "404" in refused["result"]


@pytest.mark.engine
def test_the_assistant_explains_the_failure_event_with_the_evidence_behind_it(
    twin: dict[str, Any], client: TestClient
) -> None:
    url, rid = twin["url"], twin["rec"][MAIN]
    listing = ask(url, "list_recordings", {"project": "arm"}).json()["result"]
    assert {r["label"] for r in listing} == {MAIN, FIX}
    got = ask(url, "get_recording", {"project": "arm", "recording_id": rid}).json()["result"]
    assert "summary" not in got and got["episode"]["verdict"] == "violated"
    failure = next(e for e in got["events"] if e["kind"] == "motion_continues")
    out = ask(url, "explain_recording_event", {"project": "arm", "recording_id": rid, "event_id": failure["id"]}).json()
    assert out["is_error"] is False and out["tool"] == "explain_recording_event"
    ex = out["result"]
    assert (
        ex["basis"].startswith("rule-based")
        and ex["event"]["id"] == failure["id"]
        and ex["event"]["severity"] == "problem"
    )
    text = "\n".join(f["statement"] for f in ex["findings"])
    cited = {i for f in ex["findings"] for i in f["evidence"]}
    # what the recording shows, with its rule and topics
    assert "Base still moving after the last command" in text and "/odom" in text and "Rule:" in text
    # the run identity as reported, including the dirty tree and the two files
    assert "a modified tree" in text and "gz_bridge.yaml" in text and "reported" in text
    # the engine's verdict, contract and observation for the linked episode
    detail = ok(client.get(f"{P}/evaluations/{twin['job']['id']}/episodes/{twin['eps'][MAIN]['id']}", headers=VERA))
    report = detail["verifier_report"]
    assert "violated" in text and report["contract"]["name"] in text and "1.003 m" in text and "simulated" in text
    assert {
        f"verification:{twin['eps'][MAIN]['id']}",
        f"contract:{report['contract']['sha256'].removeprefix('sha256:')[:12]}",
    } <= cited
    assert {f"recording:{rid}", f"event:{rid}/{failure['id']}"} <= cited
    assert any(i.startswith("recording-sha256:") for i in cited) and any(i.startswith("identity:") for i in cited)
    # the two views are kept apart, the data-quality event is surfaced, and what is not known is said
    assert "different measurements" in text and "moved backwards" in text
    assert any("why it happened" in n for n in ex["not_known"]) and any(
        "physical hardware" in n for n in ex["not_known"]
    )
    assert any("moved backwards" in n for n in ex["not_known"])
    # every cited recording event really exists on the recording
    for i in cited:
        if i.startswith(f"event:{rid}/"):
            assert i.split("/", 1)[1] in {e["id"] for e in got["events"]}


@pytest.mark.engine
def test_the_fix_recording_is_explained_as_stopping_and_bad_requests_are_answered_not_crashed(
    twin: dict[str, Any],
) -> None:
    url, rid = twin["url"], twin["rec"][FIX]
    ev = next(
        e
        for e in ask(url, "get_recording", {"project": "arm", "recording_id": rid}).json()["result"]["events"]
        if e["kind"] == "motion_stopped"
    )
    ex = ask(url, "explain_recording_event", {"project": "arm", "recording_id": rid, "event_id": ev["id"]}).json()[
        "result"
    ]
    text = "\n".join(f["statement"] for f in ex["findings"])
    assert "Base stopped after the last command" in text and "satisfied" in text and "a clean checkout" in text
    assert ex["event"]["severity"] == "info" and not any(f["severity"] == "bad" for f in ex["findings"])
    missing = ask(url, "explain_recording_event", {"project": "arm", "recording_id": rid, "event_id": "ev-99"}).json()
    assert missing["is_error"] is True and "no event 'ev-99'" in missing["result"] and "ev-" in missing["result"]
    bad = ask(
        url, "explain_recording_event", {"project": "arm", "recording_id": "not-a-uuid", "event_id": "ev-1"}
    ).json()
    assert bad["is_error"] is True and "invalid input" in bad["result"]


@pytest.mark.engine
def test_the_web_assistant_and_an_mcp_client_get_the_same_answer(twin: dict[str, Any]) -> None:
    url, rid = twin["url"], twin["rec"][MAIN]
    args = {"project": "arm", "recording_id": rid, "event_id": "ev-1"}
    via_http = ask(url, "explain_recording_event", args).json()["result"]
    mcp = Mcp(url, "dev:vera")
    try:
        via_mcp = mcp.data("explain_recording_event", org="lab", **args)
    finally:
        mcp.close()
    assert json.dumps(via_http, sort_keys=True) == json.dumps(via_mcp, sort_keys=True)
