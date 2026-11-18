"""The bridge against the real pinned engine and the pinned OpenMHS fixtures. No mocks."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path

import pytest
from openmhs_bridge import Engine, EngineError, conditions_of, digest

pytestmark = pytest.mark.engine


def records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def test_provenance_names_the_pinned_build(engine: Engine) -> None:
    p = engine.provenance()
    assert p.version.startswith("openmhs ")
    assert p.binary_sha256 == engine.config.expected_sha256
    assert p.commit == "e9ef873b42f74f201aecf392ee6e61453e1f40a4"
    assert p.interfaces["ops_rules_version"] == "corr-1"


def test_a_different_digest_is_refused(engine: Engine) -> None:
    other = Engine(dataclasses.replace(engine.config, expected_sha256="sha256:" + "1" * 64))
    with pytest.raises(EngineError) as info:
        other.provenance()
    assert info.value.code == "engine.digest_mismatch"


def test_gazebo_ab_verified_comparison_is_reproduced(engine: Engine, fixtures: Path, tmp_path: Path) -> None:
    store = tmp_path / "ops.sqlite"
    ingest = engine.ingest(store, [fixtures / "gazebo_ab.jsonl"]).value
    assert ingest.ingested == {"accepted": 1117, "duplicate": 4}
    assert ingest.rebuild.rules_version == "corr-1"

    res = engine.compare(store, task_type="lift", a="engine-bullet", b="tol-0.01", verified=True)
    verified, raw = res.value, res.raw
    assert res.provenance.binary_sha256 == engine.config.expected_sha256
    assert res.provenance.commit == "e9ef873b42f74f201aecf392ee6e61453e1f40a4"
    assert verified.a.attempt_outcomes == (15, 15, 0)
    assert verified.b.attempt_outcomes == (30, 0, 0)
    assert verified.a.unit == "scenario" and verified.a.scenarios == 10
    assert verified.difference_method == "newcombe"
    assert verified.difference is not None and verified.difference[0] == pytest.approx(-0.5)
    assert verified.difference[1] == pytest.approx(-0.7634069094874361)
    assert verified.a.ci95 == pytest.approx((0.236593090512564, 0.7634069094874361))
    assert verified.verdict == "insufficient_evidence"
    assert json.loads(raw)["verdict"] == "insufficient_evidence"  # raw output kept verbatim

    reported = engine.compare(store, task_type="lift", a="engine-bullet", b="tol-0.01", verified=False).value
    assert reported.outcome == "reported"
    assert (reported.a.failed, reported.b.failed) == (0, 0)


def test_python_manifest_digests_equal_the_engines(engine: Engine, fixtures: Path, tmp_path: Path) -> None:
    """RFC 0005 §3: the digest we compute for a manifest is the one the engine resolves for its release label."""
    store = tmp_path / "ops.sqlite"
    engine.ingest(store, [fixtures / "gazebo_ab.jsonl"])
    manifests = [r for r in records(fixtures / "gazebo_ab.jsonl") if r.get("schema") == "openmhs.deployment/0.1"]
    ours = {m["labels"]["release"]: set() for m in manifests}
    for m in manifests:
        ours[m["labels"]["release"]].add(digest(m))
    cmp_ = engine.compare(store, task_type="lift", a="engine-bullet", b="tol-0.01", verified=True).value
    assert set(cmp_.a.manifests) == ours["engine-bullet"]
    assert set(cmp_.b.manifests) == ours["tol-0.01"]


def test_real_flight_fixture_with_124_verdicts(engine: Engine, fixtures: Path, tmp_path: Path) -> None:
    path = fixtures / "coresense_real_flights_verified.jsonl"
    recs = records(path)
    assert len(recs) == 469
    assert sum(r.get("type") == "outcome.verified" for r in recs) == 124
    store = tmp_path / "ops.sqlite"
    ingest = engine.ingest(store, [path]).value
    assert ingest.rejected == []
    assert ingest.rebuild.incidents == 9
    incidents = engine.incidents(store).value
    assert len(incidents) == 9
    detail = engine.show(store, incidents[0].incident_id).value
    assert detail.summary.incident_id == incidents[0].incident_id
    assert detail.members


def test_paired_comparison(engine: Engine, fixtures: Path, tmp_path: Path) -> None:
    store = tmp_path / "ops.sqlite"
    engine.ingest(store, [fixtures / "policy_pusht_rollouts.jsonl"])
    c = engine.compare(store, task_type="pusht", a="ddpm-100", b="ddim-10", verified=False, paired=True).value
    assert c.paired is not None
    assert c.paired.pairs == 20
    assert c.paired.mcnemar_p == pytest.approx(0.5078125)


def test_rejected_records_fail_unless_allowed(engine: Engine, tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"schema":"openmhs.event/0.1","event_id":"x"}\n', encoding="utf-8")
    with pytest.raises(EngineError) as info:
        engine.ingest(tmp_path / "a.sqlite", [bad])
    assert info.value.code == "engine.input_rejected"
    assert "`type` is required" in info.value.detail["rejected"][0]
    result = engine.ingest(tmp_path / "b.sqlite", [bad], allow_rejections=True).value
    assert len(result.rejected) == 1


CASES = ["placed", "dropped_outside_the_tray", "camera_calibration_expired", "action_aborted_but_object_in_tray"]


@pytest.mark.parametrize("case", CASES)
def test_verifier_on_corpus_cases(engine: Engine, pinned_src: Path, tmp_path: Path, case: str) -> None:
    d = pinned_src / "research" / "outcome-verifier" / "corpus" / "cases" / "pick_place" / case
    contract = json.loads((d / "contract.json").read_text(encoding="utf-8"))
    evidence = records(d / "evidence.jsonl")
    expected = json.loads((d / "expected.json").read_text(encoding="utf-8"))["verdict"]
    res = engine.verify_outcome(contract, evidence, workdir=tmp_path, name=case)
    report, raw = res.value, res.raw
    assert report.verdict == expected
    assert report.verifier.startswith("openmhs-outcome ")
    assert len(report.conditions) == len(contract["conditions"])
    # The copied helper equals OpenMHS's own (decision D-008).
    original = _load_conditions_of(pinned_src)
    assert conditions_of(contract, json.loads(raw)) == original(contract, json.loads(raw))


def _load_conditions_of(pinned_src: Path):  # type: ignore[no-untyped-def]
    """Import OpenMHS's conditions_of from the pinned tree without installing the package."""
    import sys

    sys.path.insert(0, str(pinned_src / "python"))
    try:
        mod = importlib.import_module("openmhs.importers.coresense_verify")
        return mod.conditions_of
    finally:
        sys.path.pop(0)


def test_malformed_contract_is_an_input_error(engine: Engine, tmp_path: Path) -> None:
    with pytest.raises(EngineError) as info:
        engine.verify_outcome({"schema": "nope"}, [], workdir=tmp_path)
    assert info.value.code == "engine.input_rejected"
    assert "unknown field" in info.value.detail["stderr"]


@pytest.mark.parametrize("label", ["--verified", "--store=elsewhere.sqlite", "-h", "a b; rm -rf /"])
def test_hostile_release_labels_stay_values(engine: Engine, fixtures: Path, tmp_path: Path, label: str) -> None:
    """A label is bound as --a=<label>: the engine reads it as a selector that matches nothing, never as a flag."""
    store = tmp_path / "ops.sqlite"
    engine.ingest(store, [fixtures / "gazebo_ab.jsonl"])
    c = engine.compare(store, task_type="lift", a=label, b="tol-0.01", verified=True).value
    assert c.a.selector == label
    assert c.a.manifests == []
    assert any("matches no manifest" in w for w in c.warnings)
    assert not (tmp_path / "elsewhere.sqlite").exists()


def test_unexpected_manifest_resolution_is_an_error(engine: Engine, fixtures: Path, tmp_path: Path) -> None:
    store = tmp_path / "ops.sqlite"
    engine.ingest(store, [fixtures / "gazebo_ab.jsonl"])
    with pytest.raises(EngineError) as info:
        engine.compare(store, task_type="lift", a="no-such-release", b="tol-0.01", verified=True, expect_a={"x"})
    assert info.value.code == "engine.input_rejected"
    assert info.value.detail["resolved"] == []


def test_observers_see_every_engine_process(engine: Engine, fixtures: Path, tmp_path: Path) -> None:
    """Telemetry hook: command, timing and outcome of each process, nothing else; a failing observer is ignored."""
    from openmhs_bridge import Invocation

    seen: list[Invocation] = []

    def broken(_: Invocation) -> None:
        raise RuntimeError("observer bug")

    engine.observers[:] = [broken, seen.append]
    try:
        store = tmp_path / "ops.sqlite"
        engine.ingest(store, [fixtures / "gazebo_ab.jsonl"])
        engine.compare(store, verified=False, task_type="pick_place", a="nonexistent-a", b="nonexistent-b")
    finally:
        engine.observers.clear()
    commands = [i.command for i in seen]
    assert commands == ["ops ingest", "ops compare"], commands
    for inv in seen:
        assert inv.end_ns >= inv.start_ns
        assert inv.outcome == "ok" and inv.returncode == 0
        assert str(tmp_path) not in repr(inv)  # no paths or arguments in telemetry
