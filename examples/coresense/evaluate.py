"""Run the CoreSense real-flight evidence through the platform's API, worker and pinned engine; keep the reports.

    uv run python examples/coresense/evaluate.py --api http://127.0.0.1:8765 --baseline no_failure \
        --candidate panel_failure

Needs a running stack in development auth mode (scripts/dev_stack.py) and the CSVs from extract.py. Creates a
uniquely named organization. The two "releases" are flight CONDITIONS of the same software (the dataset names no
software revision); the release descriptions say so, and so does the README. Writes report.json and report.html
under examples/coresense/results/<baseline>__<candidate>/.
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
DESCRIPTION = {
    "no_failure": "Nominal flights (no induced failure). Same Aerostack2 software as the other conditions.",
    "panel_failure": "Flights with an experimenter-induced panel failure. Same software as no_failure.",
    "double_failure": "Flights with two experimenter-induced failures. Same software as no_failure.",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--baseline", default="no_failure", choices=sorted(DESCRIPTION))
    ap.add_argument("--candidate", default="panel_failure", choices=sorted(DESCRIPTION))
    ap.add_argument("--min-known", type=int, default=30)
    ns = ap.parse_args()
    run = format(int(time.time() * 1000), "x")
    c = httpx.Client(base_url=ns.api, headers={"Authorization": f"Bearer dev:coresense-{run}"}, timeout=120)

    def ok(r: httpx.Response, status: int = 201) -> Any:
        if r.status_code != status:
            raise SystemExit(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:500]}")
        return r.json()

    org = f"coresense-{run}"
    ok(c.post("/api/v1/orgs", json={"slug": org, "name": "CoreSense real flights"}))
    p = f"/api/v1/orgs/{org}/projects/drones"
    ok(c.post(f"/api/v1/orgs/{org}/projects", json={"slug": "drones", "name": "Crazyflie swarm"}))
    ids: dict[str, str] = {}
    for role, cond in (("baseline", ns.baseline), ("candidate", ns.candidate)):
        comp = [{"kind": "software", "name": "aerostack2", "version": "unpublished"}]
        rel = {"label": f"condition-{cond}", "kind": "software", "components": comp, "description": DESCRIPTION[cond]}
        ids[role] = ok(c.post(f"{p}/releases", json=rel))["id"]
        data = (HERE / "data" / f"{cond}.csv").read_bytes()
        ids[f"{role}_art"] = ok(c.post(f"{p}/artifacts", files={"file": (f"{cond}.csv", data, "text/csv")}))["id"]
    spec = json.loads((HERE / "mapping.json").read_text(encoding="utf-8"))
    mapping = ok(c.post(f"{p}/mappings", json=spec))["id"]
    body = {
        "baseline_release_id": ids["baseline"],
        "candidate_release_id": ids["candidate"],
        "mapping_id": mapping,
        "baseline_artifact_ids": [ids["baseline_art"]],
        "candidate_artifact_ids": [ids["candidate_art"]],
        "config": {"task_type": "goto", "paired": True, "min_known": ns.min_known, "stratify_by_site": False},
    }
    job = ok(c.post(f"{p}/evaluations", json=body))
    while job["state"] in ("queued", "running"):
        time.sleep(1)
        job = c.get(f"{p}/evaluations/{job['id']}").raise_for_status().json()
    if job["state"] != "succeeded":
        print(json.dumps(job["error"], indent=2), file=sys.stderr)
        return 1
    out = HERE / "results" / f"{ns.baseline}__{ns.candidate}"
    out.mkdir(parents=True, exist_ok=True)
    report = c.get(f"{p}/evaluations/{job['id']}/report.json").raise_for_status()
    (out / "report.json").write_bytes(report.content)
    (out / "report.html").write_bytes(c.get(f"{p}/evaluations/{job['id']}/report.html").raise_for_status().content)
    validation = c.get(f"{p}/evaluations/{job['id']}/validation").raise_for_status().json()
    (out / "validation.json").write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = {"evaluation": job["id"], "summary": job["summary"], "report_sha256": report.headers["x-report-sha256"]}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
