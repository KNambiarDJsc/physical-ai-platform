"""Tenant isolation over EVERY organization-scoped route, enumerated from the OpenAPI document (not hand-listed).

Two attacks per route, by an outsider user and by an outsider service credential:
1. the victim's organization and project slugs with the victim's resource ids  -> 404, nothing of the victim's;
2. the attacker's OWN organization and project with the victim's resource ids  -> no victim data, and 404 whenever
   a victim id is in the path or the body (the classic IDOR).
The victim's data is checked unchanged afterwards. Needs the engine (the victim has a finished evaluation).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import as_user, bearer, make_org, ok

DEMO = Path(__file__).resolve().parents[3] / "examples" / "manipulation-demo"
ID_PARAMS = {
    "user_id", "credential_id", "artifact_id", "release_id", "mapping_id", "job_id", "episode_id",
    "device_id", "run_id", "proposal_id", "recording_id", "request_id", "trial_id", "session_id",
}  # fmt: skip
pytestmark = pytest.mark.engine


def _toy() -> tuple[dict[str, Any], bytes, bytes]:
    import hashlib
    import struct

    urdf = b'<robot name="t"><link name="b"><visual><geometry><mesh filename="package://t/a.stl"/></geometry></visual></link></robot>'
    stl = b"x".ljust(80, b" ") + struct.pack("<I", 1) + b"\x00" * 50
    sha = lambda b: "sha256:" + hashlib.sha256(b).hexdigest()  # noqa: E731
    manifest = {
        "slug": "planted-model", "name": "planted", "urdf": "robot.urdf",
        "files": [{"path": "robot.urdf", "sha256": sha(urdf)}, {"path": "a.stl", "sha256": sha(stl)}],
        "source": {"repository": "x/y", "commit": "abcdef1", "license_spdx": "MIT"},
    }  # fmt: skip
    return manifest, urdf, stl


TOY_MANIFEST, TOY_URDF, TOY_STL = _toy()


def bodies(v: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Valid requests, so a 404 cannot be masked by a 422. A new route with a body needs an entry here."""
    o = "/api/v1/orgs/{org_slug}"
    p = o + "/projects/{project_slug}"
    spec = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
    return {
        ("PUT", f"{o}/members"): {"json": {"issuer": "dev", "subject": "mallory", "role": "admin"}},
        ("POST", f"{o}/service-credentials"): {"json": {"name": "x", "role": "admin"}},
        ("POST", f"{o}/projects"): {"json": {"slug": "planted", "name": "planted"}},
        ("POST", f"{p}/releases"): {
            "json": {"label": "planted", "kind": "software", "components": [{"kind": "software", "name": "x"}]}
        },
        ("POST", f"{p}/artifacts"): {"files": {"file": ("planted.csv", b"a\n1\n")}},
        ("POST", f"{p}/mappings"): {"json": dict(spec, name="planted")},
        ("POST", f"{o}/environments"): {"json": {"config_key": "virtual-lab", "slug": "planted"}},
        ("POST", f"{o}/environments/{{env_slug}}/discover"): {},
        ("POST", f"{o}/workflows"): {
            "json": {
                "slug": "planted",
                "name": "planted",
                "environment": "virtual-lab",
                "template": "dispense-and-verify",
            }
        },
        ("POST", f"{o}/workflows/{{workflow_slug}}/runs"): {},
        ("POST", f"{p}/twin/models"): {
            "data": {"manifest": json.dumps(TOY_MANIFEST)},
            "files": [
                ("files", ("robot.urdf", TOY_URDF, "application/xml")),
                ("files", ("a.stl", TOY_STL, "model/stl")),
            ],
        },
        ("POST", f"{p}/twin/recordings"): {
            "data": {"label": "planted"},
            "files": {"file": ("planted.mcap", b"\x89MCAP0\r\n", "application/octet-stream")},
        },
        ("POST", f"{o}/experiments"): {"json": {"slug": "planted", "name": "planted"}},
        ("POST", f"{o}/experiments/{{experiment_slug}}/versions"): {"json": {"spec": {}}},
        ("POST", f"{o}/experiments/{{experiment_slug}}/versions/{{number}}/requests"): {"json": {"note": "planted"}},
        ("POST", f"{o}/experiments/{{experiment_slug}}/release-evaluations"): {
            "json": {"version": 1, "baseline_arm": "a", "candidate_arm": "b"}
        },
        ("POST", f"{o}/experiment-requests/{{request_id}}/approve"): {"json": {"spec_sha256": "sha256:" + "0" * 64}},
        ("POST", f"{o}/experiment-requests/{{request_id}}/reject"): {"json": {"spec_sha256": "sha256:" + "0" * 64}},
        ("POST", f"{o}/assistant/tools/{{tool_name}}"): {"json": {"arguments": {}}},
        ("POST", f"{o}/agent/sessions"): {"json": {"question": "planted question"}},
        ("POST", f"{o}/experiment-proposals"): {"json": {"workflow": "dispense", "rationale": "planted proposal text"}},
        ("POST", f"{o}/experiment-proposals/{{proposal_id}}/approve"): {},
        ("POST", f"{o}/experiment-proposals/{{proposal_id}}/reject"): {"json": {"note": "planted"}},
        ("POST", f"{p}/evaluations"): {
            "json": {
                "baseline_release_id": v["baseline"],
                "candidate_release_id": v["candidate"],
                "mapping_id": v["mapping_id"],
                "baseline_artifact_ids": [v["artifact_id"]],
                "candidate_artifact_ids": [v["artifact_id"]],
                "config": {"task_type": "pick_place"},
            }
        },
    }


def org_routes() -> list[tuple[str, str]]:
    """(method, path) for every path with an organization in it, from the generated OpenAPI document.

    FastAPI 0.163 includes routers lazily, so ``app.routes`` does not list them; the OpenAPI document is the
    complete public contract (test_no_hidden_routes checks nothing is excluded from it).
    """
    from app.routes import register  # the same registration create_app() uses
    from fastapi import FastAPI

    app = FastAPI()
    register(app)
    out = []
    for path, ops in app.openapi()["paths"].items():
        if "{org_slug}" in path:
            out.extend((m.upper(), path) for m in sorted(ops) if m in ("get", "post", "put", "patch", "delete"))
    return out


def test_no_hidden_routes() -> None:
    import ast

    app_dir = Path(__file__).resolve().parents[1] / "app"
    for f in app_dir.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.keyword) and node.arg == "include_in_schema":
                raise AssertionError(f"{f}: include_in_schema hides a route from the isolation test")


def test_every_route_with_a_body_has_one_here() -> None:
    routes = org_routes()
    assert len(routes) >= 25, routes  # sanity: the enumeration found every router
    with_body = {(m, p) for m, p in routes if m in ("POST", "PUT", "PATCH") and not p.endswith("/cancel")}
    missing = with_body - set(bodies({k: "x" for k in ("baseline", "candidate", "mapping_id", "artifact_id")}))
    assert not missing, f"add a valid body for {missing} so isolation is tested, not validation"


@pytest.fixture
def world(
    client: TestClient, omhs: Any, with_lab: str, sim_host: str, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    from test_jobs import P, work_once

    h = as_user("alice")
    victim = make_org(client, "alice", "acme", "picking")  # same slugs test_jobs uses
    v: dict[str, Any] = {"org_slug": "acme", "project_slug": "picking"}
    v["user_id"] = ok(client.get("/api/v1/me", headers=h))["id"]
    v["credential_id"] = ok(
        client.post("/api/v1/orgs/acme/service-credentials", json={"name": "victim-ci", "role": "admin"}, headers=h),
        201,
    )["id"]
    for key in ("baseline", "candidate"):
        comp = [{"kind": "software", "name": "pick-stack", "version": key}]
        v[key] = ok(
            client.post(
                f"{P}/releases", json={"label": f"victim-{key}", "kind": "software", "components": comp}, headers=h
            ),
            201,
        )["id"]
        data = (DEMO / "data" / f"{key}.csv").read_bytes()
        v[f"{key}_art"] = ok(client.post(f"{P}/artifacts", files={"file": (f"{key}.csv", data)}, headers=h), 201)["id"]
    v["release_id"], v["artifact_id"] = v["baseline"], v["baseline_art"]
    spec = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
    v["mapping_id"] = ok(client.post(f"{P}/mappings", json=spec, headers=h), 201)["id"]
    job = ok(
        client.post(
            f"{P}/evaluations",
            json={
                "baseline_release_id": v["baseline"],
                "candidate_release_id": v["candidate"],
                "mapping_id": v["mapping_id"],
                "baseline_artifact_ids": [v["baseline_art"]],
                "candidate_artifact_ids": [v["candidate_art"]],
                "config": {"task_type": "pick_place"},
            },
            headers=h,
        ),
        201,
    )
    assert work_once() == "succeeded"
    v["job_id"] = job["id"]
    v["episode_id"] = ok(client.get(f"{P}/evaluations/{job['id']}/episodes?limit=1", headers=h))["items"][0]["id"]
    # Hardware Hub: the victim's environment and its discovered devices.
    ok(client.post("/api/v1/orgs/acme/environments", json={"config_key": "virtual-lab"}, headers=h), 201)
    found = ok(client.post("/api/v1/orgs/acme/environments/virtual-lab/discover", headers=h))["devices"]
    v["env_slug"], v["name"] = "virtual-lab", "simulated"
    v["device_id"] = next(d["id"] for d in found if d["key"] == "pump")
    # Workflows: the victim's workflow and one queued run.
    wf = {
        "slug": "dispense",
        "name": "victim-workflow",
        "environment": "virtual-lab",
        "template": "dispense-and-verify",
    }
    ok(client.post("/api/v1/orgs/acme/workflows", json=wf, headers=h), 201)
    v["workflow_slug"] = "dispense"
    v["session_id"] = ok(
        client.post("/api/v1/orgs/acme/agent/sessions", json={"question": "victim question"}, headers=h), 202
    )["id"]  # a real session of the victim's (the runner is the test stand-in)
    v["run_id"] = ok(client.post("/api/v1/orgs/acme/workflows/dispense/runs", headers=h), 201)["id"]
    prop = {"workflow": "dispense", "rationale": "victim-proposal-rationale", "evidence_ids": ["run:victim"]}
    v["proposal_id"] = ok(client.post("/api/v1/orgs/acme/experiment-proposals", json=prop, headers=h), 201)["id"]
    # Digital twin: the victim's robot model version and a recording of theirs.
    from test_twin_recordings import FIX, run_files

    manifest = dict(TOY_MANIFEST, slug="victim-model", name="victim-model")
    ok(
        client.post(
            f"{P}/twin/models",
            data={"manifest": json.dumps(manifest)},
            files=[("files", ("robot.urdf", TOY_URDF, "application/xml")), ("files", ("a.stl", TOY_STL, "model/stl"))],
            headers=h,
        ),
        201,
    )
    mcap, summary, identity, _ = run_files(FIX)
    rec = client.post(
        f"{P}/twin/recordings",
        data={"label": "victim-recording", "summary": json.dumps(summary), "identity": json.dumps(identity)},
        files={"file": ("victim.mcap", mcap, "application/octet-stream")},
        headers=h,
    )
    v["recording_id"] = ok(rec, 201)["id"]
    v["model_slug"], v["number"], v["file_path"] = "victim-model", 1, "robot.urdf"
    v["tool_name"] = "list_workspaces"
    # Experiments: the victim's environment with a simulation host, an experiment, a version, an approved request and
    # its trials (so the artifact route has a real trial to refuse).
    from app.config import get_settings

    cat = json.loads(os.environ["PAP_ENVIRONMENTS"])
    cat.append({"key": "selftest-sim", "name": "Self-test host", "kind": "simulated", "endpoint": sim_host})
    monkeypatch.setenv("PAP_ENVIRONMENTS", json.dumps(cat))
    get_settings.cache_clear()
    ok(client.post("/api/v1/orgs/acme/environments", json={"config_key": "selftest-sim"}, headers=h), 201)
    ok(client.post("/api/v1/orgs/acme/environments/selftest-sim/discover", headers=h))
    ok(
        client.post(
            "/api/v1/orgs/acme/experiments", json={"slug": "victim-exp", "name": "victim-experiment"}, headers=h
        ),
        201,
    )
    sims = {e["slug"]: e for e in ok(client.get("/api/v1/orgs/acme/simulation-environments", headers=h))}
    sc = next(s for s in sims["selftest-sim"]["scenarios"] if s["id"] == "selftest-drive")
    spec = {
        "environment": "selftest-sim",
        "simulator": sims["selftest-sim"]["simulator"],
        "scenario": {"id": "selftest-drive", "version": "1", "definition_sha256": sc["definition_sha256"]},
        "software": [{"name": "victim-controller", "revision": "1"}],
        "arms": [{"key": "only", "parameters": {"stop_on_command_loss": True}}],
        "limits": {"max_trials": 1, "max_wall_time_s": 60},
        "observations": {"measurements": ["travel_after_kill_m"], "artifacts": []},
        "contract": {"name": "victim-contract", "version": "1", "conditions": [
            {"name": "victim condition", "measurement": "travel_after_kill_m", "op": "le", "value": 1}]},
    }  # fmt: skip
    ver = ok(client.post("/api/v1/orgs/acme/experiments/victim-exp/versions", json={"spec": spec}, headers=h), 201)
    # a second principal for the approval that is not a member (membership is asserted unchanged below)
    cred = {"name": "victim-reviewer", "role": "engineer"}
    reviewer = ok(client.post("/api/v1/orgs/acme/service-credentials", json=cred, headers=h), 201)
    req = ok(client.post("/api/v1/orgs/acme/experiments/victim-exp/versions/1/requests", json={}, headers=h), 201)
    appr = ok(
        client.post(
            f"/api/v1/orgs/acme/experiment-requests/{req['id']}/approve",
            json={"spec_sha256": ver["spec_sha256"]},
            headers=bearer(reviewer["token"]),
        )
    )
    v["experiment_slug"], v["request_id"] = "victim-exp", req["id"]
    v["trial_id"] = appr["trial_results"][0]["id"]
    secrets = {
        v[k]
        for k in ("user_id", "credential_id", "baseline", "candidate", "baseline_art", "candidate_art", "mapping_id",
                  "job_id", "episode_id", "device_id", "run_id", "proposal_id", "recording_id", "request_id",
                  "trial_id", "session_id")
    } | {victim["org"]["id"], victim["project"]["id"], "victim-ci", "victim-baseline", "victim-candidate",
         "victim question",
         "victim-proposal-rationale",
         "victim-workflow", "victim-recording", "victim-model", "victim-experiment", "victim-controller",
         "victim-contract", "victim condition", "victim-reviewer"}  # fmt: skip
    make_org(client, "mallory", "mallory-co", "mallory-proj")
    mcred = ok(
        client.post("/api/v1/orgs/mallory-co/service-credentials", json={"name": "m", "role": "admin"},
                    headers=as_user("mallory")),
        201,
    )  # fmt: skip
    return {"v": v, "secrets": secrets, "outsiders": [as_user("mallory"), bearer(mcred["token"])]}


def _call(c: TestClient, method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None) -> Any:
    return c.request(method, url, headers=headers, **(body or {}))


def test_outsiders_cannot_reach_the_victim(client: TestClient, world: dict[str, Any]) -> None:
    v, secrets = world["v"], world["secrets"]
    body_for = bodies(v)
    failures = []
    for method, path in org_routes():
        params = set(re.findall(r"{(\w+)}", path))
        assert params <= set(v), f"isolation test needs a victim value for {params - set(v)}"
        body = body_for.get((method, path))
        for headers in world["outsiders"]:
            # 1. the victim's own path
            r = _call(client, method, path.format(**v), headers, body)
            if r.status_code != 404 or any(s in r.text for s in secrets):
                failures.append(f"victim path {method} {path}: {r.status_code} {r.text[:200]}")
            # 2. the attacker's path with the victim's ids (IDOR)
            own = dict(v, org_slug="mallory-co", project_slug="mallory-proj")
            r = _call(client, method, path.format(**own), headers, body)
            if any(s in r.text for s in secrets):
                failures.append(f"IDOR {method} {path}: leaked victim data: {r.text[:200]}")
            carries_victim_id = bool(params & ID_PARAMS) or (method, path) == (
                "POST",
                "/api/v1/orgs/{org_slug}/projects/{project_slug}/evaluations",
            )
            if carries_victim_id and r.status_code != 404:
                failures.append(f"IDOR {method} {path}: expected 404, got {r.status_code} {r.text[:200]}")
    assert not failures, "\n".join(failures)
    # the victim's data is unchanged
    h = as_user("alice")
    assert [p["slug"] for p in ok(client.get("/api/v1/orgs/acme/projects", headers=h))] == ["picking"]
    assert [m["subject"] for m in ok(client.get("/api/v1/orgs/acme/members", headers=h))] == ["alice"]
    rel = ok(client.get("/api/v1/orgs/acme/projects/picking/releases", headers=h))
    assert sorted(r["label"] for r in rel) == ["victim-baseline", "victim-candidate"]
    assert len(ok(client.get("/api/v1/orgs/acme/projects/picking/evaluations", headers=h))) == 1


def test_me_lists_only_own_organizations(client: TestClient, world: dict[str, Any]) -> None:
    me = ok(client.get("/api/v1/me", headers=as_user("mallory")))
    assert [o["slug"] for o in me["organizations"]] == ["mallory-co"]
