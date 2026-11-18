"""Run the evaluation pipeline once on the synthetic demo dataset with the pinned engine, without the database.

    uv run python scripts/run_demo_pipeline.py [--out DIR]

Prints the validation summary, outcome classes per release, and both engine comparisons. Useful to inspect what the
engine says before writing assertions; the API and worker run the same function.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.contracts.episode import EvaluationConfig  # noqa: E402
from app.contracts.mapping import MappingSpec  # noqa: E402
from app.evaluations.pipeline import ArtifactInput, PipelineInput, ReleaseInput, run_pipeline  # noqa: E402
from openmhs_bridge import engine_from_env, sha256_bytes  # noqa: E402

DEMO = ROOT / "examples" / "manipulation-demo"


def demo_input(paired: bool = False) -> PipelineInput:
    spec = MappingSpec.model_validate_json((DEMO / "mapping.json").read_text(encoding="utf-8"))

    def release(label: str, version: str, csv_name: str) -> ReleaseInput:
        data = (DEMO / "data" / csv_name).read_bytes()
        manifest = {
            "schema": "openmhs.deployment/0.1",
            "components": [{"kind": "software", "name": "pick-stack", "version": version}],
            "labels": {"release": label},
        }
        return ReleaseInput(label, manifest, (ArtifactInput(sha256_bytes(data), data, csv_name),))

    return PipelineInput(
        organization="demo",
        project="warehouse",
        baseline=release("pick-stack-2.14.0", "2.14.0", "baseline.csv"),
        candidate=release("pick-stack-2.15.0-rc1", "2.15.0-rc1", "candidate.csv"),
        mapping=spec,
        mapping_ref="warehouse-pick-csv@1",
        config=EvaluationConfig(task_type="pick_place", paired=paired),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ns = ap.parse_args()
    out = Path(ns.out) if ns.out else Path(tempfile.mkdtemp(prefix="pap-demo-"))
    engine = engine_from_env(ROOT / "engine.lock.json")
    res = run_pipeline(engine, demo_input(paired=True), out)
    for a in res.validation["artifacts"]:
        codes = Counter(r["code"] for r in a["rejections"])
        print(f"{a['release']}: rows {a['rows']} episodes {a['episodes']} rejected {a['rejected']} {dict(codes)}")
    for label in (res.reported.a.selector, res.reported.b.selector):
        c = Counter(e.outcome_class for e in res.episodes if e.mapped.episode.release == label)
        print(f"{label}: {dict(sorted(c.items()))}")
    for name, raw in (("reported", res.reported_raw), ("verified", res.verified_raw), ("paired", res.paired_raw)):
        if raw is None:
            continue
        d = json.loads(raw)
        print(f"\n{name}: verdict {d['verdict']}  difference {d['difference']}")
        for arm in ("a", "b"):
            x = d[arm]
            print(
                f"  {arm} {x['selector']}: unit {x['unit']} ok {x['succeeded']} failed {x['failed']} "
                f"unknown {x['unknown']} rate {x['rate']} ci95 {x['ci95']} attempts {x['attempt_outcomes']}"
            )
        print(f"  reasons {d['reasons']}\n  warnings {d['warnings']}")
        if d.get("paired"):
            print(f"  paired {d['paired']}")
    print(f"\nengine {res.provenance.version} {res.provenance.binary_sha256[:19]}; bundle in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
