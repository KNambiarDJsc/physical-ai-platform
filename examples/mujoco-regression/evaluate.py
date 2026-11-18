"""Run the pre-registered comparisons of the MuJoCo experiment through the platform; keep reports and timings.

    uv run python examples/mujoco-regression/evaluate.py --api http://127.0.0.1:8765

Needs a stack in development auth mode (scripts/dev_stack.py) and data/*.csv from `sim.py run`. Writes
results/<A>__<X>/{report.json,report.html,validation.json} and results/timings.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
RELEASES = {
    "A": ("controller-latency-10ms", "Baseline controller, 10 ms command latency."),
    "B": ("controller-latency-50ms", "Same controller with 50 ms command latency (injected regression)."),
    "C": ("controller-latency-10ms-rerun", "Identical to the baseline (same configuration hash), independent seeds."),
    "D": ("controller-latency-20ms", "Same controller with 20 ms command latency (secondary regression)."),
}
COMPARISONS = (("A", "B", True), ("A", "D", True), ("A", "C", False))  # pre-registered; paired = same seeds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ns = ap.parse_args()
    run = format(int(time.time() * 1000), "x")
    c = httpx.Client(base_url=ns.api, headers={"Authorization": f"Bearer dev:mujoco-{run}"}, timeout=120)

    def ok(r: httpx.Response, status: int = 201) -> Any:
        if r.status_code != status:
            raise SystemExit(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:500]}")
        return r.json()

    timings: dict[str, Any] = {}
    t0 = time.perf_counter()
    org = f"mujoco-{run}"
    ok(c.post("/api/v1/orgs", json={"slug": org, "name": "MuJoCo regression experiment"}))
    p = f"/api/v1/orgs/{org}/projects/reach"
    ok(c.post(f"/api/v1/orgs/{org}/projects", json={"slug": "reach", "name": "Planar arm reaching"}))
    rel, art = {}, {}
    for g, (label, desc) in RELEASES.items():
        comp = [{"kind": "software", "name": "reach-controller", "version": label}]
        rel[g] = ok(c.post(f"{p}/releases", json={"label": label, "kind": "software", "components": comp,
                                                  "description": desc}))["id"]  # fmt: skip
        data = (HERE / "data" / f"{g}.csv").read_bytes()
        art[g] = ok(c.post(f"{p}/artifacts", files={"file": (f"{g}.csv", data, "text/csv")}))["id"]
    mapping = ok(c.post(f"{p}/mappings", json=json.loads((HERE / "mapping.json").read_text(encoding="utf-8"))))["id"]
    timings["import_s"] = round(time.perf_counter() - t0, 2)

    results: dict[str, Any] = {}
    for a, b, paired in COMPARISONS:
        t1 = time.perf_counter()
        body = {
            "baseline_release_id": rel[a],
            "candidate_release_id": rel[b],
            "mapping_id": mapping,
            "baseline_artifact_ids": [art[a]],
            "candidate_artifact_ids": [art[b]],
            "config": {
                "task_type": "reach",
                "paired": paired,
                "min_known": 30,
                "margin": 0.01,
                "stratify_by_site": False,
            },
        }
        job = ok(c.post(f"{p}/evaluations", json=body))
        while job["state"] in ("queued", "running"):
            time.sleep(0.5)
            job = c.get(f"{p}/evaluations/{job['id']}").raise_for_status().json()
        if job["state"] != "succeeded":
            print(json.dumps(job["error"], indent=2), file=sys.stderr)
            return 1
        timings[f"{a}__{b}_verdict_s"] = round(time.perf_counter() - t1, 2)
        out = HERE / "results" / f"{a}__{b}"
        out.mkdir(parents=True, exist_ok=True)
        report = c.get(f"{p}/evaluations/{job['id']}/report.json").raise_for_status()
        (out / "report.json").write_bytes(report.content)
        (out / "report.html").write_bytes(c.get(f"{p}/evaluations/{job['id']}/report.html").raise_for_status().content)
        val = c.get(f"{p}/evaluations/{job['id']}/validation").raise_for_status().json()
        (out / "validation.json").write_text(json.dumps(val, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        results[f"{a}__{b}"] = {"summary": job["summary"], "report_sha256": report.headers["x-report-sha256"]}
    (HERE / "results" / "timings.json").write_text(json.dumps(timings, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"timings": timings, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
