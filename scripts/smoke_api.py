"""Smoke test of a running stack over HTTP: one real evaluation of the synthetic demo, then the reports.

    uv run python scripts/smoke_api.py --api http://127.0.0.1:8765

Needs a stack in development auth mode (scripts/dev_stack.py or Compose). Creates a uniquely named organization;
it changes nothing else. Exit code 0 only if every check holds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "manipulation-demo"


def check(cond: bool, what: str) -> None:
    print(("ok   " if cond else "FAIL ") + what, flush=True)
    if not cond:
        raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--timeout", type=float, default=300)
    ns = ap.parse_args()
    run = format(int(time.time() * 1000), "x")
    org, user = f"smoke-{run}", f"smoke-{run}"
    c = httpx.Client(base_url=ns.api, headers={"Authorization": f"Bearer dev:{user}"}, timeout=60)

    def ok(r: httpx.Response, status: int = 200) -> Any:
        check(r.status_code == status, f"{r.request.method} {r.request.url.path} -> {r.status_code}")
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r

    ok(c.get("/healthz"))
    ok(c.post("/api/v1/orgs", json={"slug": org, "name": "Smoke"}), 201)
    p = f"/api/v1/orgs/{org}/projects/picking"
    ok(c.post(f"/api/v1/orgs/{org}/projects", json={"slug": "picking", "name": "Picking"}), 201)
    ids: dict[str, str] = {}
    for key, label in (("baseline", "2.14.0"), ("candidate", "2.15.0-rc1")):
        comp = [{"kind": "software", "name": "pick-stack", "version": label}]
        ids[key] = ok(c.post(f"{p}/releases", json={"label": label, "kind": "software", "components": comp}), 201)["id"]
        data = (DEMO / "data" / f"{key}.csv").read_bytes()
        ids[f"{key}_art"] = ok(c.post(f"{p}/artifacts", files={"file": (f"{key}.csv", data, "text/csv")}), 201)["id"]
    spec = json.loads((DEMO / "mapping.json").read_text(encoding="utf-8"))
    mapping = ok(c.post(f"{p}/mappings", json=spec), 201)["id"]
    body = {
        "baseline_release_id": ids["baseline"],
        "candidate_release_id": ids["candidate"],
        "mapping_id": mapping,
        "baseline_artifact_ids": [ids["baseline_art"]],
        "candidate_artifact_ids": [ids["candidate_art"]],
        "config": {"task_type": "pick_place", "paired": True},
    }
    job = ok(c.post(f"{p}/evaluations", json=body), 201)
    deadline = time.monotonic() + ns.timeout
    while job["state"] in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(1)
        job = c.get(f"{p}/evaluations/{job['id']}").raise_for_status().json()
    check(job["state"] == "succeeded", f"evaluation {job['id']} succeeded (state {job['state']}, error {job['error']})")
    check(job["summary"]["verdict_reported"] == "improvement", "reported comparison: improvement")
    check(job["summary"]["verdict_verified"] == "insufficient_evidence", "verified comparison: insufficient evidence")
    check(job["provenance"]["evidence_class"] == ["synthetic"], "evidence class recorded as synthetic")
    a = c.get(f"{p}/evaluations/{job['id']}/report.json")
    b = c.get(f"{p}/evaluations/{job['id']}/report.json")
    check(a.status_code == 200 and a.content == b.content, "JSON report is byte-identical when generated twice")
    check(a.headers["x-report-sha256"] == "sha256:" + hashlib.sha256(a.content).hexdigest(), "report digest header")
    h = c.get(f"{p}/evaluations/{job['id']}/report.html")
    check(h.status_code == 200 and "SYNTHETIC EVIDENCE" in h.text, "HTML report states the evidence class")
    check(a.headers["x-report-sha256"] in h.text, "HTML report names the JSON report it was rendered from")
    outsider = httpx.get(
        f"{ns.api}{p}/evaluations/{job['id']}/report.json", headers={"Authorization": "Bearer dev:nobody"}, timeout=30
    )
    check(outsider.status_code == 404, "a user outside the organization gets 404")
    print(f"smoke passed: evaluation {job['id']}, report {a.headers['x-report-sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
