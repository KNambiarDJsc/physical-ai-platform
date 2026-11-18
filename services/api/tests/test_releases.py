"""RI-001 releases and DATA-003 mapping revisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import as_user, make_org, ok

P = "/api/v1/orgs/acme/projects/picking"
DEMO = Path(__file__).resolve().parents[3] / "examples" / "manipulation-demo"


@pytest.fixture
def proj(client: TestClient) -> TestClient:
    make_org(client, "alice", "acme", "picking")
    return client


def release(c: TestClient, label: str, **over: Any) -> Any:
    body = {"label": label, "kind": "software", "components": [{"kind": "software", "name": "pick", "version": label}]}
    body.update(over)
    return c.post(f"{P}/releases", json=body, headers=as_user("alice"))


def test_release_manifest_and_digest(proj: TestClient) -> None:
    r = ok(release(proj, "2.14.0"), 201)
    assert r["manifest"]["schema"] == "openmhs.deployment/0.1"
    assert r["manifest"]["labels"] == {"release": "2.14.0"}
    assert r["manifest_digest"].startswith("sha256:")
    assert release(proj, "2.14.0").status_code == 409
    assert len(ok(proj.get(f"{P}/releases", headers=as_user("alice")))) == 1


def test_policy_release_needs_an_immutable_model_revision(proj: TestClient) -> None:
    tag = [{"kind": "model", "name": "grasp", "revision": "hf://acme/grasp@main"}]
    r = release(proj, "p1", kind="policy", components=tag)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "release.model_revision"
    pinned = [{"kind": "model", "name": "grasp", "revision": "hf://acme/grasp@84a7c2318c4f2b1e"}]
    ok(release(proj, "p2", kind="policy", components=pinned), 201)
    digest = [{"kind": "model", "name": "grasp", "checkpoint_digest": "sha256:" + "a" * 64}]
    ok(release(proj, "p3", kind="policy", components=digest), 201)


def test_floats_the_engine_could_digest_differently_are_refused(proj: TestClient) -> None:
    comps = [{"kind": "config", "name": "gripper", "force_n": 1e-7}]
    r = release(proj, "f1", components=comps)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "release.manifest"


@pytest.mark.engine
def test_release_digest_equals_the_engines(proj: TestClient, omhs: Any, tmp_path: Path) -> None:
    r = ok(release(proj, "2.15.0", components=[{"kind": "software", "name": "pick", "version": "2.15.0",
                                                "config": {"speed": 0.25, "retries": 3}}]), 201)  # fmt: skip
    event = {
        "schema": "openmhs.event/0.1", "event_id": "e1", "type": "task.ended", "provenance": "imported",
        "source": {"id": "t", "kind": "import"}, "scope": {"tenant": "t", "robot": "r"},
        "time": {"observed": "2026-11-02T08:00:00Z", "clock_domain": "c"},
        "subject": {"task_id": "k", "task_type": "pick"}, "deployment": {"manifest": r["manifest_digest"]},
        "outcome": {"reported": {"value": "succeeded"}},
    }  # fmt: skip
    f = tmp_path / "e.jsonl"
    f.write_text(json.dumps(r["manifest"]) + "\n" + json.dumps(event) + "\n", encoding="utf-8")
    omhs.ingest(tmp_path / "s.sqlite", [f])
    c = omhs.compare(tmp_path / "s.sqlite", task_type="pick", a="2.15.0", b="2.15.0", verified=False).value
    assert c.a.manifests == [r["manifest_digest"]]
    assert c.a.attempts == 1


def test_mapping_revisions_are_immutable_versions(proj: TestClient) -> None:
    spec = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
    v1 = ok(proj.post(f"{P}/mappings", json=spec, headers=as_user("alice")), 201)
    assert v1["version"] == 1 and v1["spec_sha256"].startswith("sha256:")
    same = proj.post(f"{P}/mappings", json=spec, headers=as_user("alice"))
    assert same.status_code == 200 and same.json()["id"] == v1["id"]
    spec["contract"]["window_ms"] = [0, 5000]
    v2 = ok(proj.post(f"{P}/mappings", json=spec, headers=as_user("alice")), 201)
    assert v2["version"] == 2 and v2["spec_sha256"] != v1["spec_sha256"]
    assert ok(proj.get(f"{P}/mappings/{v1['id']}", headers=as_user("alice")))["spec"]["contract"]["window_ms"] == [
        0,
        3000,
    ]
    for method in ("put", "patch", "delete"):
        assert getattr(proj, method)(f"{P}/mappings/{v1['id']}", headers=as_user("alice")).status_code == 405


def test_invalid_mapping_is_422_with_reasons(proj: TestClient) -> None:
    spec = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
    spec["contract"]["conditions"][0]["evidence"] = "nope"
    r = proj.post(f"{P}/mappings", json=spec, headers=as_user("alice"))
    assert r.status_code == 422 and "unknown measurements" in r.text
