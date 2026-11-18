"""RI-003 core: the pipeline on the synthetic demo dataset with the REAL pinned engine (no mocks)."""

from __future__ import annotations

import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from app.evaluations.pipeline import ArtifactInput, PipelineError, run_pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from run_demo_pipeline import demo_input

pytestmark = pytest.mark.engine


@pytest.fixture(scope="module")
def result(omhs: Any, tmp_path_factory: pytest.TempPathFactory) -> Any:
    return run_pipeline(omhs, demo_input(paired=True), tmp_path_factory.mktemp("demo"))


def test_validation_report_accounts_for_every_row(result: Any) -> None:
    for a in result.validation["artifacts"]:
        assert (a["rows"], a["episodes"], a["rejected"]) == (123, 120, 3)
        assert sorted(r["code"] for r in a["rejections"]) == ["row.reported", "row.required", "row.time"]


def test_outcome_classes(result: Any) -> None:
    by = {
        label: Counter(e.outcome_class for e in result.episodes if e.mapped.episode.release == label)
        for label in ("pick-stack-2.14.0", "pick-stack-2.15.0-rc1")
    }
    assert by["pick-stack-2.14.0"] == {
        "supported_success": 84,
        "verified_failure": 24,
        "contradiction": 7,
        "unknown": 5,
    }
    assert by["pick-stack-2.15.0-rc1"] == {
        "supported_success": 77,
        "contradiction": 25,
        "unknown": 9,
        "verified_failure": 9,
    }
    # an unknown always says why, from the verifier's reason codes
    unknowns = [e for e in result.episodes if e.outcome_class == "unknown"]
    assert all(e.reasons for e in unknowns)
    assert {"evidence.missing", "evidence.quality", "evidence.outside_window"} & {
        r for e in unknowns for r in e.reasons
    }


def test_reported_and_verified_comparisons_disagree_honestly(result: Any) -> None:
    rep, ver = result.reported, result.verified
    assert rep.outcome == "reported" and ver.outcome == "verified"
    assert rep.a.attempt_outcomes == (96, 24, 0) and rep.b.attempt_outcomes == (111, 9, 0)
    assert rep.verdict == "improvement"
    assert ver.a.attempt_outcomes == (84, 31, 5) and ver.b.attempt_outcomes == (77, 34, 9)
    assert ver.verdict == "insufficient_evidence"
    assert ver.a.unit == "scenario" and ver.a.scenarios == 40
    assert json.loads(result.paired_raw)["paired"]["pairs"] == 32


def test_engine_accepted_every_event(result: Any) -> None:
    lines = result.events_path.read_text(encoding="utf-8").splitlines()
    assert result.ingest["rejected"] == []
    assert sum(result.ingest["ingested"].values()) == len(lines)
    assert result.ingest["ingested"].get("duplicate", 0) == 0


def test_result_equals_a_direct_cli_run_on_the_same_events(omhs: Any, result: Any, tmp_path: Path) -> None:
    store = tmp_path / "again.sqlite"
    omhs.ingest(store, [result.events_path])
    again = omhs.compare(
        store, task_type="pick_place", a="pick-stack-2.14.0", b="pick-stack-2.15.0-rc1", verified=True, min_known=30,
        margin=0.01,
    )  # fmt: skip
    assert again.raw == result.verified_raw


def test_deterministic(omhs: Any, result: Any, tmp_path: Path) -> None:
    second = run_pipeline(omhs, demo_input(paired=True), tmp_path)
    assert second.events_path.read_bytes() == result.events_path.read_bytes()
    assert second.verified_raw == result.verified_raw and second.reported_raw == result.reported_raw


def test_provenance_names_the_engine(result: Any) -> None:
    assert result.provenance.commit == "e9ef873b42f74f201aecf392ee6e61453e1f40a4"
    assert result.reported.rules_version == "corr-1"


def test_same_release_twice_is_refused(omhs: Any, tmp_path: Path) -> None:
    inp = demo_input()
    with pytest.raises(PipelineError) as info:
        run_pipeline(omhs, dataclasses.replace(inp, candidate=inp.baseline), tmp_path)
    assert info.value.code == "input.same_release"


def test_unknown_task_type_is_refused(omhs: Any, tmp_path: Path) -> None:
    inp = demo_input()
    cfg = inp.config.model_copy(update={"task_type": "welding"})
    with pytest.raises(PipelineError) as info:
        run_pipeline(omhs, dataclasses.replace(inp, config=cfg), tmp_path)
    assert info.value.code == "input.task_type" and info.value.detail["found"] == ["pick_place"]


def test_rejected_artifact_fails_the_whole_evaluation(omhs: Any, tmp_path: Path) -> None:
    inp = demo_input()
    bad = ArtifactInput("sha256:bad", b"\xff\xfe garbage", "bad.csv")
    cand = dataclasses.replace(inp.candidate, artifacts=(*inp.candidate.artifacts, bad))
    with pytest.raises(PipelineError) as info:
        run_pipeline(omhs, dataclasses.replace(inp, candidate=cand), tmp_path)
    assert info.value.code == "input.artifact_rejected" and info.value.detail["code"] == "input.encoding"


@pytest.mark.parametrize(
    ("reported", "verdict", "evidence", "expected"),
    [
        ("succeeded", "satisfied", True, "supported_success"),
        ("succeeded", "violated", True, "contradiction"),
        ("failed", "satisfied", True, "contradiction"),
        ("failed", "violated", True, "verified_failure"),
        ("timeout", "satisfied", True, "contradiction"),
        ("aborted", "violated", True, "verified_failure"),
        # A cancelled goal claims nothing: the evidence alone decides, it is never a contradiction.
        ("canceled", "satisfied", True, "verified_success"),
        ("canceled", "violated", True, "verified_failure"),
        ("unknown", "satisfied", True, "verified_success"),
        ("succeeded", "unknown", True, "unknown"),
        ("succeeded", None, False, "reported_only"),
        ("unknown", None, False, "insufficient_evidence"),
    ],
)
def test_outcome_class_table(reported: str, verdict: str | None, evidence: bool, expected: str) -> None:
    from app.evaluations.pipeline import outcome_class

    assert outcome_class(reported, verdict, evidence) == expected
