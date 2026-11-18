"""RI-002..RI-005 through the API, the worker code and the REAL engine (no mocks)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import as_user, make_org, ok
from sqlalchemy import select

P = "/api/v1/orgs/acme/projects/picking"
DEMO = Path(__file__).resolve().parents[3] / "examples" / "manipulation-demo"
pytestmark = pytest.mark.engine


@pytest.fixture
def demo(client: TestClient, omhs: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from app.config import get_settings

    monkeypatch.setenv("PAP_WORKER_LEASE_S", "5")
    get_settings.cache_clear()
    make_org(client, "alice", "acme", "picking")
    h = as_user("alice")
    ids: dict[str, Any] = {}
    for key, label, version in (("baseline", "pick-stack-2.14.0", "2.14.0"), ("candidate", "pick-stack-2.15.0-rc1",
                                                                             "2.15.0-rc1")):  # fmt: skip
        comp = [{"kind": "software", "name": "pick-stack", "version": version}]
        ids[key] = ok(client.post(f"{P}/releases", json={"label": label, "kind": "software", "components": comp},
                                  headers=h), 201)["id"]  # fmt: skip
        data = (DEMO / "data" / f"{key}.csv").read_bytes()
        ids[f"{key}_art"] = ok(client.post(f"{P}/artifacts", files={"file": (f"{key}.csv", data)}, headers=h), 201)[
            "id"
        ]
    spec = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
    ids["mapping"] = ok(client.post(f"{P}/mappings", json=spec, headers=h), 201)["id"]
    ids["body"] = {
        "baseline_release_id": ids["baseline"],
        "candidate_release_id": ids["candidate"],
        "mapping_id": ids["mapping"],
        "baseline_artifact_ids": [ids["baseline_art"]],
        "candidate_artifact_ids": [ids["candidate_art"]],
        "config": {"task_type": "pick_place", "paired": True},
    }
    return ids


def submit(c: TestClient, body: dict[str, Any], status: int = 201) -> Any:
    return ok(c.post(f"{P}/evaluations", json=body, headers=as_user("alice")), status)


def work_once() -> str | None:
    """One claim + execute, exactly as the worker process does."""
    from app.config import get_settings
    from app.db import session_factory
    from app.evaluations import service
    from app.workers.run import execute

    with session_factory()() as s:
        job_id = service.claim(s, "test-worker", get_settings().worker_lease_s)
    return execute(job_id, "test-worker") if job_id else None


def test_full_evaluation(client: TestClient, demo: dict[str, Any], omhs: Any, tmp_path: Path) -> None:
    job = submit(client, demo["body"])
    assert job["state"] == "queued" and job["attempts"] == 0
    assert submit(client, demo["body"], 200)["id"] == job["id"]  # idempotent by input checksum
    assert client.get(f"{P}/evaluations/{job['id']}/comparison", headers=as_user("alice")).status_code == 409

    assert work_once() == "succeeded"
    j = ok(client.get(f"{P}/evaluations/{job['id']}", headers=as_user("alice")))
    assert j["state"] == "succeeded" and j["attempts"] == 1
    assert j["summary"]["verdict_reported"] == "improvement"
    assert j["summary"]["verdict_verified"] == "insufficient_evidence"
    assert j["summary"]["rejected_rows"] == 6
    prov = j["provenance"]
    assert prov["engine"]["commit"] == "e9ef873b42f74f201aecf392ee6e61453e1f40a4"
    assert prov["engine"]["binary_sha256"] == omhs.config.expected_sha256
    assert prov["rules_version"] == "corr-1" and prov["evidence_class"] == ["synthetic"]
    assert prov["mapping"].startswith("warehouse-pick-csv@1 sha256:")
    assert prov["input_sha256"] == job["input_sha256"]

    # RI-005: the comparison is the engine's output, unchanged
    cmp_ = ok(client.get(f"{P}/evaluations/{job['id']}/comparison", headers=as_user("alice")))
    if os.environ.get("PAP_WRITE_WEB_FIXTURE") == "1":  # a real API response for the web component tests
        out = Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "test" / "comparison.fixture.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cmp_, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    assert json.loads(cmp_["verified"]["raw"]) == cmp_["verified"]["result"]
    assert cmp_["verified"]["result"]["b"]["attempt_outcomes"] == [77, 34, 9]
    assert cmp_["reported"]["result"]["verdict"] == "improvement"
    assert cmp_["paired"]["result"]["paired"]["pairs"] == 32

    # RI-004: re-running the engine on the stored events file reproduces the stored output byte for byte
    from app.db import session_factory
    from app.evidence.models import Artifact
    from app.evidence.storage import get_storage

    with session_factory()() as s:
        events = s.scalar(select(Artifact).where(Artifact.sha256 == prov["bundle"]["events"]))
        assert events is not None and events.kind == "events"
        path = get_storage().path(events.storage_key)
    store = tmp_path / "again.sqlite"
    omhs.ingest(store, [path])
    again = omhs.compare(store, task_type="pick_place", a="pick-stack-2.14.0", b="pick-stack-2.15.0-rc1",
                         verified=True, min_known=30, margin=0.01)  # fmt: skip
    assert again.raw == cmp_["verified"]["raw"]
    assert "sha256:" + __import__("hashlib").sha256(again.raw.encode()).hexdigest() == cmp_["verified"]["raw_sha256"]

    # RI-005 / RI-007: episodes, filters, detail with the verifier's reasons
    page = ok(client.get(f"{P}/evaluations/{job['id']}/episodes?outcome_class=contradiction&limit=500",
                         headers=as_user("alice")))  # fmt: skip
    assert page["total"] == 32 and all(e["outcome_class"] == "contradiction" for e in page["items"])
    cand = ok(client.get(f"{P}/evaluations/{job['id']}/episodes?release_id={demo['candidate']}&limit=1",
                         headers=as_user("alice")))  # fmt: skip
    assert cand["total"] == 120 and len(cand["items"]) == 1
    unknown = ok(client.get(f"{P}/evaluations/{job['id']}/episodes?outcome_class=unknown", headers=as_user("alice")))
    detail = ok(client.get(f"{P}/evaluations/{job['id']}/episodes/{unknown['items'][0]['id']}",
                           headers=as_user("alice")))  # fmt: skip
    assert detail["verifier_report"]["verdict"] == "UNKNOWN" and detail["reasons"]
    assert detail["document"]["organization"] == "acme" and detail["document"]["evidence_class"] == "synthetic"
    assert detail["document"]["source"]["row"] == detail["source_row"]
    val = ok(client.get(f"{P}/evaluations/{job['id']}/validation", headers=as_user("alice")))
    assert sum(a["rejected"] for a in val["artifacts"]) == 6
    assert isinstance(ok(client.get(f"{P}/evaluations/{job['id']}/incidents", headers=as_user("alice"))), list)


def test_cancel_queued(client: TestClient, demo: dict[str, Any]) -> None:
    job = submit(client, demo["body"])
    c = ok(client.post(f"{P}/evaluations/{job['id']}/cancel", headers=as_user("alice")))
    assert c["state"] == "cancelled"
    assert work_once() is None  # nothing left to claim
    assert client.post(f"{P}/evaluations/{job['id']}/cancel", headers=as_user("alice")).status_code == 409


def test_cancel_running_kills_the_engine(client: TestClient, demo: dict[str, Any]) -> None:
    from app.config import get_settings
    from app.db import session_factory
    from app.evaluations import service
    from app.workers.run import execute

    job = submit(client, demo["body"])
    with session_factory()() as s:
        job_id = service.claim(s, "w1", get_settings().worker_lease_s)
    ok(client.post(f"{P}/evaluations/{job['id']}/cancel", headers=as_user("alice")))  # running: flag only
    assert execute(job_id, "w1") == "cancelled"  # type: ignore[arg-type]
    j = ok(client.get(f"{P}/evaluations/{job['id']}", headers=as_user("alice")))
    assert j["state"] == "cancelled" and j["summary"] is None


def test_timeout_fails_after_bounded_attempts(client: TestClient, demo: dict[str, Any]) -> None:
    from app.db import session_factory
    from app.evaluations.models import EvaluationJob

    job = submit(client, demo["body"])
    with session_factory()() as s:
        row = s.get(EvaluationJob, job["id"])
        assert row is not None
        row.timeout_s, row.max_attempts = 1, 1
        s.commit()
    assert work_once() == "failed"
    j = ok(client.get(f"{P}/evaluations/{job['id']}", headers=as_user("alice")))
    assert j["state"] == "failed" and j["error"]["code"] == "job.timeout" and j["attempts"] == 1


def test_transient_failure_is_retried_then_fails(
    client: TestClient, demo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient engine error (here: the binary cannot start) re-queues the job until max_attempts."""
    from app.engine import get_engine
    from openmhs_bridge import EngineError

    job = submit(client, demo["body"])

    def broken(*a: Any, **k: Any) -> Any:
        raise EngineError("engine.start_failed", "simulated start failure")

    monkeypatch.setattr(get_engine(), "verify_outcome", broken)
    assert work_once() == "queued"
    assert work_once() == "queued"
    assert work_once() == "failed"
    j = ok(client.get(f"{P}/evaluations/{job['id']}", headers=as_user("alice")))
    assert j["attempts"] == 3 and j["error"]["code"] == "engine.start_failed"


def test_invalid_submissions(client: TestClient, demo: dict[str, Any]) -> None:
    same = dict(demo["body"], candidate_release_id=demo["baseline"])
    r = client.post(f"{P}/evaluations", json=same, headers=as_user("alice"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "input.same_release"
    foreign = dict(demo["body"], mapping_id="00000000-0000-0000-0000-000000000001")
    assert client.post(f"{P}/evaluations", json=foreign, headers=as_user("alice")).status_code == 404
    wrong_type = dict(demo["body"], config={"task_type": "welding"})
    job = submit(client, wrong_type)
    assert work_once() == "failed"
    j = ok(client.get(f"{P}/evaluations/{job['id']}", headers=as_user("alice")))
    assert j["error"]["code"] == "input.task_type" and j["error"]["detail"]["found"] == ["pick_place"]


def test_concurrent_workers_never_claim_the_same_job(client: TestClient, demo: dict[str, Any]) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from app.db import session_factory
    from app.evaluations import service

    submit(client, demo["body"])

    def claim(i: int) -> Any:
        with session_factory()() as s:
            return service.claim(s, f"w{i}", 30)

    with ThreadPoolExecutor(max_workers=8) as pool:
        claimed = [c for c in pool.map(claim, range(8)) if c is not None]
    assert len(claimed) == 1
