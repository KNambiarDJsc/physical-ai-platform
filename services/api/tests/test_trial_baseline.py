"""The trial's conventional baseline script computes the same numbers as the engine on the shipped data.

If this fails, the "equivalent task definitions" claim in trial/README.md is false: fix the script or the README,
never the expected values. Engine outputs are read from the committed reports, not recomputed here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "trial" / "baseline"))
import analysis  # noqa: E402

CASES = [
    ("mujoco", "A", "B", "examples/mujoco-regression/results/A__B"),
    ("mujoco", "A", "D", "examples/mujoco-regression/results/A__D"),
    ("mujoco", "A", "C", "examples/mujoco-regression/results/A__C"),
    ("coresense", "no_failure", "panel_failure", "examples/coresense/results/no_failure__panel_failure"),
    ("coresense", "no_failure", "double_failure", "examples/coresense/results/no_failure__double_failure"),
]


def engine_output(path: str, kind: str) -> dict[str, Any] | None:
    report = json.loads((ROOT / path / "report.json").read_text(encoding="utf-8"))
    out = report["engine_outputs"].get(kind)
    return json.loads(out["raw"]) if out else None


@pytest.mark.parametrize(("dataset", "a", "b", "path"), CASES)
@pytest.mark.parametrize(
    ("key", "kind"), [("reported_fail", "compare_reported"), ("verified_fail", "compare_verified")]
)
def test_baseline_matches_engine(dataset: str, a: str, b: str, path: str, key: str, kind: str) -> None:
    load = analysis.mujoco if dataset == "mujoco" else analysis.coresense
    mine = analysis.compare(analysis.by_scenario(load(a), key), analysis.by_scenario(load(b), key))
    eng = engine_output(path, kind)
    assert eng is not None
    for arm in ("a", "b"):
        e = eng[arm]
        assert mine[arm] == (e["failed"], e["scenarios"] - e["unknown"]), f"{arm} counts"
        k, n = mine[arm]
        assert analysis.wilson(k, n) == pytest.approx(tuple(e["ci95"]), abs=1e-9), f"{arm} interval"
    assert mine["verdict"] == eng["verdict"]
    if "difference" in mine:
        assert mine["difference"] == pytest.approx(tuple(eng["difference"]), abs=1e-9)


@pytest.mark.parametrize(("dataset", "a", "b", "path"), [c for c in CASES if c[2] != "C"])
def test_baseline_mcnemar_matches_engine(dataset: str, a: str, b: str, path: str) -> None:
    load = analysis.mujoco if dataset == "mujoco" else analysis.coresense
    mine = analysis.compare(
        analysis.by_scenario(load(a), "verified_fail"), analysis.by_scenario(load(b), "verified_fail")
    )
    paired = engine_output(path, "compare_paired")
    assert paired is not None and paired["paired"] is not None
    p = paired["paired"]
    assert (mine["a_only_fails"], mine["b_only_fails"]) == (p["a_only_fails"], p["b_only_fails"])
    assert mine["mcnemar_p"] == pytest.approx(p["mcnemar_p"], rel=1e-9)
