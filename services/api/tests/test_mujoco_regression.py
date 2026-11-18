"""Milestone C: the controlled MuJoCo regression experiment, re-checked from the committed files.

1. The simulation regenerates every committed rollout byte for byte from the committed code and seeds.
2. The pre-registered comparisons, run through the real pipeline and pinned engine, give the recorded verdicts.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from app.contracts.episode import EvaluationConfig
from app.contracts.mapping import MappingSpec
from app.evaluations.pipeline import ArtifactInput, PipelineInput, ReleaseInput, run_pipeline
from openmhs_bridge import sha256_bytes

EXP = Path(__file__).resolve().parents[3] / "examples" / "mujoco-regression"
LABEL = {"A": "controller-latency-10ms", "B": "controller-latency-50ms", "C": "controller-latency-10ms-rerun",
         "D": "controller-latency-20ms"}  # fmt: skip


def test_rollouts_regenerate_byte_for_byte(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    sys.path.insert(0, str(EXP))
    try:
        import sim
    finally:
        sys.path.remove(str(EXP))
    manifest = json.loads((EXP / "data" / "manifest.json").read_text(encoding="utf-8"))
    n = manifest["n_per_group"]
    for i, (group, meta) in enumerate(sorted(manifest["groups"].items())):
        assert meta["config_sha256"] == sim.GROUPS[group].sha256(), f"{group}: configuration changed since the run"
        seeds = range(sim.SEEDS[group].start, sim.SEEDS[group].start + n)
        assert [seeds.start, seeds.stop] == meta["seeds"]
        rows, _ = sim.rollouts(group, seeds, i * 10_000)
        digest = sim.write(rows, tmp_path / f"{group}.csv")
        assert digest == meta["csv_sha256"], f"{group}: regenerated rollouts differ from the committed ones"
        committed = (EXP / "data" / f"{group}.csv").read_bytes()
        assert "sha256:" + hashlib.sha256(committed).hexdigest() == meta["csv_sha256"]
    # A and C run the identical controller; only their seeds differ.
    assert manifest["groups"]["A"]["config_sha256"] == manifest["groups"]["C"]["config_sha256"]


def release(group: str) -> ReleaseInput:
    data = (EXP / "data" / f"{group}.csv").read_bytes()
    manifest = {
        "schema": "openmhs.deployment/0.1",
        "components": [{"kind": "software", "name": "reach-controller", "version": LABEL[group]}],
        "labels": {"release": LABEL[group]},
    }
    return ReleaseInput(LABEL[group], manifest, (ArtifactInput(sha256_bytes(data), data, f"{group}.csv"),))


def evaluate(omhs: Any, a: str, b: str, paired: bool, work: Path) -> Any:
    spec = MappingSpec.model_validate_json((EXP / "mapping.json").read_text(encoding="utf-8"))
    inp = PipelineInput(
        organization="mujoco-experiment",
        project="reach",
        baseline=release(a),
        candidate=release(b),
        mapping=spec,
        mapping_ref="mujoco-reach-ground-truth@1",
        config=EvaluationConfig(task_type="reach", paired=paired, min_known=30, margin=0.01, stratify_by_site=False),
    )
    return run_pipeline(omhs, inp, work)


@pytest.mark.engine
@pytest.mark.parametrize(
    ("a", "b", "paired", "reported", "verified", "failed_b"),
    [
        ("A", "B", True, "regression", "regression", 146),  # primary injected regression
        ("A", "D", True, "regression", "regression", 32),  # secondary, smaller physical effect
        ("A", "C", False, "insufficient_evidence", "insufficient_evidence", 0),  # no-change control
    ],
)
def test_preregistered_comparisons(
    omhs: Any, tmp_path: Path, a: str, b: str, paired: bool, reported: str, verified: str, failed_b: int
) -> None:
    out = evaluate(omhs, a, b, paired, tmp_path)
    assert sum(x["rejected"] for x in out.validation["artifacts"]) == 0
    assert len(out.episodes) == 300
    assert out.reported.verdict == reported
    assert out.verified is not None and out.verified.verdict == verified
    assert out.verified.a.failed == 0 and out.verified.b.failed == failed_b
    # The no-change control must never produce a regression or improvement verdict.
    if b == "C":
        assert out.verified.verdict not in ("regression", "improvement")
        assert out.reported.verdict not in ("regression", "improvement")
    classes = {e.outcome_class for e in out.episodes}
    assert "unknown" not in classes  # every episode has its measurement
