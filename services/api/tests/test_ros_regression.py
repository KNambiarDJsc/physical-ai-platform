"""ROS-004: the command-timeout regression of openamr-platform-sw issue #79 / PR #177, from recorded Gazebo runs,
through the existing evidence engine. Nothing here simulates a run: the inputs are result files the user's own scripts
wrote on 2026-11-20 (examples/openamr-cmd-timeout/recorded), listed with their sha256."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from app.contracts.episode import EvaluationConfig
from app.contracts.mapping import MappingSpec
from app.evaluations.pipeline import ArtifactInput, PipelineInput, ReleaseInput, run_pipeline
from fastapi.testclient import TestClient
from helpers import as_user, make_org, ok
from openmhs_bridge import sha256_bytes

EXP = Path(__file__).resolve().parents[3] / "examples" / "openamr-cmd-timeout"
RUNS = json.loads((EXP / "runs.json").read_text(encoding="utf-8"))
LIMIT_M = RUNS["upstream"]["pass_criterion"]["max_travel_after_kill_m"]
LABEL = {
    "main": "openamr-platform-sw-69847ab-main",
    "fix": "openamr-platform-sw-505d17a-fix79",
}
COMPONENTS = {
    "main": [
        {"kind": "software", "name": "openamr-platform-sw", "version": "69847ab"},
        {"kind": "config", "name": "gz_simulator wiring", "version": "origin/main"},
    ],
    "fix": [
        {"kind": "software", "name": "openamr-platform-sw", "version": "505d17a"},
        {"kind": "config", "name": "sim_cmd_vel_timeout", "version": "0.2 s simulation time, non-latching"},
    ],
}


def recorded(run: dict[str, Any]) -> float:
    raw = json.loads((EXP / RUNS["evidence"][run["id"]]["file"]).read_text(encoding="utf-8"))
    return float(raw.get("result", raw)["travel_after_kill_m"])


def test_the_episode_files_are_rebuilt_exactly_from_the_hashed_recordings() -> None:
    r = subprocess.run(
        [sys.executable, str(EXP / "build.py"), "build", "--check"], capture_output=True, text=True, check=False
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(RUNS["runs"]) == len(RUNS["evidence"]) == 11
    for run in RUNS["runs"]:  # every run directory that holds a result is listed, none is skipped or repeated
        assert RUNS["evidence"][run["id"]]["sha256"] and len(RUNS["evidence"][run["id"]]["sha256"]) == 64
    assert {r["arm"] for r in RUNS["runs"]} == {"main", "fix"}
    assert all(r["software_exact"] in (True, False) for r in RUNS["runs"])


def test_the_scenario_run_carries_its_own_identity_and_a_bag_that_matches_its_summary() -> None:
    import hashlib

    run = next(r for r in RUNS["runs"] if "bag" in r.get("extras", []))
    d = EXP / "recorded" / run["id"]
    identity = json.loads((d / "pap-run-identity.json").read_text(encoding="utf-8"))
    assert identity["run_id"] == run["id"] and identity["software"]["commit"] == RUNS["upstream"]["fix_commit"]
    assert identity["software"]["tree_dirty"] is False and identity["scenario"]["commanded_m_per_s"] == 0.2
    summary = json.loads((d / "bag-summary.json").read_text(encoding="utf-8"))
    assert summary["schema"] == "pap.ros.bag-summary/1" and summary["identity"] == identity
    mcap = next(f for f in summary["files"] if f["name"].endswith(".mcap"))
    assert (
        hashlib.sha256((d / "bag" / mcap["name"]).read_bytes()).hexdigest() == mcap["sha256"]
    )  # the bag is the one summarised
    assert summary["clock"]["monotonic"] and {t["name"] for t in summary["topics"]} >= {"/clock", "/cmd_vel", "/odom"}
    # the recorded travel is under upstream's limit, from the same run
    assert recorded(run) <= LIMIT_M


def test_the_threshold_is_upstreams_own() -> None:
    assert LIMIT_M == 0.15 == RUNS["upstream"]["pass_criterion"]["max_travel_after_kill_m"]
    mapping = json.loads((EXP / "mapping.json").read_text(encoding="utf-8"))
    cond = mapping["contract"]["conditions"][0]
    assert cond["op"] == "le" and cond["value"] == {"value": LIMIT_M, "unit": "m"}


def release(arm: str) -> ReleaseInput:
    data = (EXP / "data" / f"{arm}.csv").read_bytes()
    manifest = {"schema": "openmhs.deployment/0.1", "components": COMPONENTS[arm], "labels": {"release": LABEL[arm]}}
    return ReleaseInput(LABEL[arm], manifest, (ArtifactInput(sha256_bytes(data), data, f"{arm}.csv"),))


@pytest.mark.engine
def test_the_real_engine_judges_each_recorded_run_and_says_insufficient_evidence_for_the_comparison(
    omhs: Any, tmp_path: Path
) -> None:
    spec = MappingSpec.model_validate_json((EXP / "mapping.json").read_text(encoding="utf-8"))
    inp = PipelineInput(
        organization="openamr", project="cmd-timeout", baseline=release("main"), candidate=release("fix"), mapping=spec,
        mapping_ref="openamr-cmd-timeout-ground-truth@1",
        config=EvaluationConfig(task_type="command_loss_stop", paired=False, min_known=30, stratify_by_site=False),
    )  # fmt: skip
    out = run_pipeline(omhs, inp, tmp_path)
    assert sum(x["rejected"] for x in out.validation["artifacts"]) == 0
    by_id = {e.mapped.episode.episode_key: e for e in out.episodes}
    assert len(by_id) == 11
    # Independent expectation from the recorded files and upstream's limit, not from the pipeline.
    for run in RUNS["runs"]:
        over = recorded(run) > LIMIT_M
        assert by_id[run["id"]].outcome_class == ("verified_failure" if over else "verified_success"), run["id"]
    assert {r["arm"] for r in RUNS["runs"] if recorded(r) > LIMIT_M} == {"main"}  # only the unfixed base runs on
    # With 4 and 7 recorded runs the engine does not claim a verdict, and neither do we.
    assert out.verified is not None and out.verified.verdict == "insufficient_evidence"
    assert out.verified.a.failed == 4 and out.verified.b.failed == 0
    assert any("fewer than 30" in r for r in out.verified.reasons)
    assert out.reported.verdict == "insufficient_evidence"  # no controller report exists for these runs: all unknown
    assert {e.outcome_class for e in out.episodes} == {"verified_failure", "verified_success"}


@pytest.mark.engine
def test_the_report_is_reproducible_labelled_simulated_and_carries_the_run_identities(
    client: TestClient, omhs: Any
) -> None:
    from test_jobs import work_once

    h = as_user("rae")
    make_org(client, "rae", "openamr", "cmd-timeout")
    p = "/api/v1/orgs/openamr/projects/cmd-timeout"
    rel, art = {}, {}
    for arm in ("main", "fix"):
        release_body = {"label": LABEL[arm], "kind": "software", "components": COMPONENTS[arm]}
        rel[arm] = ok(client.post(f"{p}/releases", json=release_body, headers=h), 201)["id"]
        csv_bytes = (EXP / "data" / f"{arm}.csv").read_bytes()
        art[arm] = ok(client.post(f"{p}/artifacts", files={"file": (f"{arm}.csv", csv_bytes)}, headers=h), 201)["id"]
    mapping = ok(
        client.post(f"{p}/mappings", json=json.loads((EXP / "mapping.json").read_text(encoding="utf-8")), headers=h),
        201,
    )["id"]
    body = {
        "baseline_release_id": rel["main"], "candidate_release_id": rel["fix"], "mapping_id": mapping,
        "baseline_artifact_ids": [art["main"]], "candidate_artifact_ids": [art["fix"]],
        "config": {"task_type": "command_loss_stop", "paired": False, "min_known": 30, "stratify_by_site": False},
    }  # fmt: skip
    job = ok(client.post(f"{p}/evaluations", json=body, headers=h), 201)
    assert work_once() == "succeeded"
    url = f"{p}/evaluations/{job['id']}/report.json"
    first, second = client.get(url, headers=h), client.get(url, headers=h)
    assert first.status_code == 200 and first.content == second.content  # byte-identical
    html = client.get(f"{p}/evaluations/{job['id']}/report.html", headers=h)
    assert html.status_code == 200 and b"simulated" in html.content.lower()
    text = first.content.decode()
    assert '"simulated"' in text and "openamr-cmd-timeout-ground-truth" in text
    comp = ok(client.get(f"{p}/evaluations/{job['id']}/comparison", headers=h))
    assert comp["verified"]["result"]["verdict"] == "insufficient_evidence"
    releases = {r["label"]: r for r in ok(client.get(f"{p}/releases", headers=h))}
    versions = {c["version"] for r in releases.values() for c in r["manifest"]["components"]}
    assert {"69847ab", "505d17a"} <= versions  # the run identities are on the releases
    eps = ok(client.get(f"{p}/evaluations/{job['id']}/episodes?limit=50", headers=h))["items"]
    assert len(eps) == 11 and {e["outcome_class"] for e in eps} == {"verified_failure", "verified_success"}
