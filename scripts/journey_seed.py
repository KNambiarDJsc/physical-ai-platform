"""Prepare a clean workspace for the Laboratory experiment journey (docs/demo/RUNBOOK.md) on a running stack.

It creates only the setup a researcher would have before starting: the people, the connected and discovered virtual
laboratory, and the two procedures (a normal bench and a bench with a simulated partial blockage), each with the same
50 µL volume and an explicit ±2 % tolerance. It runs nothing, requests nothing and approves nothing: the request, the
second person's approval, the runs, the investigation and the export are the journey itself. Idempotent.

    uv run python scripts/journey_seed.py [--api http://127.0.0.1:8000] [--org lab-journey]

People (development sign-in at /settings): ada (admin, the researcher), bob (engineer, the approver), vic (viewer).
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx

PEOPLE = {"ada": "admin", "bob": "engineer", "vic": "viewer"}
PROCEDURES = [
    {
        "slug": "dispense-50ul",
        "name": "Dispense 50 µL (normal bench)",
        "template": "dispense-and-verify",
        "parameters": {"volume_ul": 50, "tolerance_pct": 2},
    },
    {
        "slug": "dispense-50ul-blocked-line",
        "name": "Dispense 50 µL (simulated partial blockage)",
        "template": "dispense-with-fault",
        "parameters": {"volume_ul": 50, "tolerance_pct": 2, "fault": "partial_blockage"},
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--org", default="lab-journey")
    ns = ap.parse_args()
    c = httpx.Client(base_url=ns.api, headers={"Authorization": "Bearer dev:ada"}, timeout=60)
    o = f"/api/v1/orgs/{ns.org}"

    def ok(r: httpx.Response, *codes: int) -> Any:
        if r.status_code not in (codes or (200,)):
            print(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:300]}", file=sys.stderr)
            sys.exit(1)
        return r.json() if r.content else None

    ok(c.post("/api/v1/orgs", json={"slug": ns.org, "name": "Laboratory experiment journey"}), 201, 409)
    for who, role in PEOPLE.items():
        ok(c.put(f"{o}/members", json={"issuer": "dev", "subject": who, "role": role}))
    ok(c.post(f"{o}/environments", json={"config_key": "virtual-lab"}), 201, 409)
    ok(c.post(f"{o}/environments/virtual-lab/discover"), 200)
    found = sorted(d["key"] for d in ok(c.get(f"{o}/devices")) if d["environment"] == "virtual-lab")
    print("devices discovered in virtual-lab:", ", ".join(found))
    missing = {"pump", "balance", "simulation"} - set(found)
    if missing:
        print(f"the virtual laboratory did not offer {sorted(missing)}: is it running?", file=sys.stderr)
        return 1
    for p in PROCEDURES:
        ok(c.post(f"{o}/workflows", json={**p, "environment": "virtual-lab"}), 201, 409)
        print("procedure ready:", p["slug"])
    print(
        f"\ndone. Sign in at /settings as ada (researcher), bob (approver) or vic (viewer); open /journey?org={ns.org}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
