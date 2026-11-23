# ruff: noqa: E501 - data-heavy seeding literals read better on one line
"""Seed a running development stack (scripts/dev_stack.py, dev sign-in) with a demonstration workspace, from real data:

* the recorded OpenAMRobot command-timeout regression (#79): two releases, their evidence, the engine's comparison, and
  the two real Gazebo recordings in the Digital twin on upstream's robot model (pre-fix and fix);
* a workflow composed across the virtual laboratory's pump and balance, with a finished run and the engine's verdict;
* a simulation experiment on the self-test host (baseline vs candidate), requested, approved by a second engineer and
  executed by the worker, ready to be judged as releases.

Nothing here is invented: every measurement comes from the recorded runs or from a real run on the stack. It is
idempotent (run it twice and nothing is duplicated). Users: ada (admin), bob (engineer), vic (viewer); sign in at /settings.

    uv run python scripts/demo_seed.py [--api http://127.0.0.1:8000] [--org demo]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "examples" / "openamr-cmd-timeout"
MAIN, FIX = "main_20261122T053012Z", "fix_20261121T185851Z"
LABEL = {"main": "openamr-platform-sw-69847ab-main", "fix": "openamr-platform-sw-505d17a-fix79"}


class Seeder:
    def __init__(self, api: str, org: str) -> None:
        self.org = org
        self.c = httpx.Client(base_url=api, timeout=300, headers={"Authorization": "Bearer dev:ada"})
        self.as_bob = {"Authorization": "Bearer dev:bob"}

    def ok(self, r: httpx.Response, *codes: int) -> Any:
        if r.status_code not in (codes or (200, 201)):
            raise SystemExit(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    def say(self, msg: str) -> None:
        print(f"  {msg}", flush=True)

    def wait(self, what: str, fn: Any, seconds: int = 300) -> Any:
        end = time.time() + seconds
        while time.time() < end:
            v = fn()
            if v:
                return v
            time.sleep(1.5)
        raise SystemExit(f"timed out waiting for {what} (is the worker running?)")


def seed(s: Seeder) -> dict[str, str]:
    o = f"/api/v1/orgs/{s.org}"
    print("workspace and people")
    s.ok(s.c.post("/api/v1/orgs", json={"slug": s.org, "name": "Demo lab"}), 201, 409)
    for who, role in (("bob", "engineer"), ("vic", "viewer")):
        s.ok(s.c.put(f"{o}/members", json={"issuer": "dev", "subject": who, "role": role}))
    catalog = {e["key"] for e in s.ok(s.c.get("/api/v1/environment-catalog"))}
    print("environments:", ", ".join(sorted(catalog)) or "none offered")
    for key in sorted(catalog):
        s.ok(s.c.post(f"{o}/environments", json={"config_key": key}), 201, 409)
        s.ok(s.c.post(f"{o}/environments/{key}/discover"), 200)

    print("recorded OpenAMRobot regression (#79): releases, evidence, engine comparison")
    s.ok(s.c.post(f"{o}/projects", json={"slug": "cmd", "name": "Command timeout (#79)"}), 201, 409)
    P = f"{o}/projects/cmd"
    rel: dict[str, str] = {}
    art: dict[str, str] = {}
    for arm in ("main", "fix"):
        comps = (
            [{"kind": "software", "name": "openamr-platform-sw", "version": "69847ab"}, {"kind": "config", "name": "gz_simulator wiring", "version": "origin/main"}]
            if arm == "main"
            else [{"kind": "software", "name": "openamr-platform-sw", "version": "505d17a"}, {"kind": "config", "name": "sim_cmd_vel_timeout", "version": "0.2 s simulation time, non-latching"}]
        )  # fmt: skip
        r = s.c.post(f"{P}/releases", json={"label": LABEL[arm], "kind": "software", "components": comps})
        rel[arm] = (
            s.ok(r, 201, 409)
            if r.status_code == 201
            else next(x for x in s.ok(s.c.get(f"{P}/releases")) if x["label"] == LABEL[arm])
        )["id"]
        data = (EXP / "data" / f"{arm}.csv").read_bytes()
        art[arm] = s.ok(s.c.post(f"{P}/artifacts", files={"file": (f"{arm}.csv", data, "text/csv")}), 200, 201)["id"]
    mapping = s.ok(
        s.c.post(f"{P}/mappings", json=json.loads((EXP / "mapping.json").read_text(encoding="utf-8"))), 200, 201
    )["id"]
    cfg = {"task_type": "command_loss_stop", "paired": False, "min_known": 30, "stratify_by_site": False}
    job = s.ok(s.c.post(f"{P}/evaluations", json={"baseline_release_id": rel["main"], "candidate_release_id": rel["fix"], "mapping_id": mapping,
                                                 "baseline_artifact_ids": [art["main"]], "candidate_artifact_ids": [art["fix"]], "config": cfg}), 200, 201)  # fmt: skip
    job = s.wait(
        "the evaluation",
        lambda: (j := s.ok(s.c.get(f"{P}/evaluations/{job['id']}"))) and j["state"] in ("succeeded", "failed") and j,
    )
    s.say(f"evaluation {job['state']}")
    eps = {e["episode_key"]: e["id"] for e in s.ok(s.c.get(f"{P}/evaluations/{job['id']}/episodes?limit=100"))["items"]}

    print("robot model and the two real Gazebo recordings in the Digital twin")
    man = json.loads((EXP / "model" / "manifest.json").read_text(encoding="utf-8"))
    files = [
        ("files", (Path(f["path"]).name, (EXP / "model" / f["path"]).read_bytes(), "application/octet-stream"))
        for f in man["files"]
    ]
    s.ok(s.c.post(f"{P}/twin/models", data={"manifest": json.dumps(man)}, files=files), 200, 201)
    for run in (MAIN, FIX):
        d = EXP / "recorded" / run
        form = {"label": run, "summary": (d / "bag-summary.json").read_text(encoding="utf-8"), "identity": (d / "pap-run-identity.json").read_text(encoding="utf-8"),
                "model_slug": man["slug"], "model_version": "1"}  # fmt: skip
        if run in eps:
            form["episode_id"] = eps[run]
        s.ok(
            s.c.post(
                f"{P}/twin/recordings",
                data=form,
                files={"file": (f"{run}.mcap", (d / "bag" / "bag_0.mcap").read_bytes(), "application/octet-stream")},
            ),
            200,
            201,
        )

    out = {"project": "cmd", "model": man["slug"]}
    envs = {e["slug"] for e in s.ok(s.c.get(f"{o}/environments"))}
    if "virtual-lab" in envs:
        print("workflow across the virtual laboratory, run by the worker, judged by the engine")
        wf = {
            "slug": "dispense-50ul",
            "name": "Dispense 50 µL and verify",
            "environment": "virtual-lab",
            "template": "dispense-and-verify",
            "parameters": {"volume_ul": 50, "tolerance_pct": 2},
        }
        s.ok(s.c.post(f"{o}/workflows", json=wf), 201, 409)
        run = s.ok(s.c.post(f"{o}/workflows/dispense-50ul/runs"), 201)
        done = s.wait(
            "the workflow run",
            lambda: (r := s.ok(s.c.get(f"{o}/workflow-runs/{run['id']}")))
            and r["state"] not in ("queued", "running")
            and r,
        )
        s.say(f"run {done['state']}, engine verdict {done.get('verdict')}")
    if "selftest-sim" in envs:
        print("experiment on the self-test simulation host (baseline vs candidate)")
        sims = {e["slug"]: e for e in s.ok(s.c.get(f"{o}/simulation-environments"))}
        env = sims["selftest-sim"]
        sc = next(x for x in env["scenarios"] if x["id"] == "selftest-drive")
        spec = {
            "environment": "selftest-sim", "simulator": env["simulator"],
            "scenario": {"id": sc["id"], "version": sc["version"], "definition_sha256": sc["definition_sha256"]},
            "model": {"project": "cmd", "model": man["slug"], "version": 1},
            "software": [{"name": "selftest-drive", "revision": "demo"}],
            "initial_conditions": {"speed_mps": 0.3, "drive_s": 1.0}, "seeds": [1, 2, 3], "repetitions": 3,
            "arms": [{"key": "pre-fix", "title": "Pre-fix", "role": "baseline", "parameters": {"stop_on_command_loss": False}},
                     {"key": "fix", "title": "Fix", "role": "candidate", "parameters": {"stop_on_command_loss": True}}],
            "limits": {"max_trials": 6, "max_wall_time_s": 600},
            "observations": {"measurements": ["travel_after_kill_m", "driven_before_kill_m"], "artifacts": ["recording"], "recording": "recording"},
            "contract": {"name": "stops-after-command-loss", "version": "1", "conditions": [{"name": "Travel after command loss is at most 0.15 m", "measurement": "travel_after_kill_m", "op": "le", "value": 0.15}]},
        }  # fmt: skip
        s.ok(
            s.c.post(
                f"{o}/experiments",
                json={
                    "slug": "stop-on-command-loss",
                    "name": "Stop on command loss",
                    "description": "Does the base stop when its commands stop? (self-test kinematic model, not a simulator)",
                },
            ),
            201,
            409,
        )
        v = s.ok(s.c.post(f"{o}/experiments/stop-on-command-loss/versions", json={"spec": spec}), 200, 201)
        runs = s.ok(s.c.get(f"{o}/experiments/stop-on-command-loss"))["requests"]
        if not any(r["state"] == "approved" for r in runs):
            req = s.ok(
                s.c.post(
                    f"{o}/experiments/stop-on-command-loss/versions/{v['number']}/requests", json={"note": "demo run"}
                ),
                201,
            )
            s.ok(
                s.c.post(
                    f"{o}/experiment-requests/{req['id']}/approve",
                    json={"spec_sha256": v["spec_sha256"]},
                    headers=s.as_bob,
                )
            )
            d = s.wait(
                "the trials",
                lambda: (r := s.ok(s.c.get(f"{o}/experiment-requests/{req['id']}")))
                and r["trials_done"] == r["trials"]
                and all(t["capture_state"] != "pending" for t in r["trial_results"])
                and r,
            )
            s.say(
                f"{d['trials_done']} trials finished: "
                + ", ".join(f"{t['arm']} {t['verdict']}" for t in d["trial_results"])
            )
            s.ok(
                s.c.post(
                    f"{o}/experiments/stop-on-command-loss/release-evaluations",
                    json={"version": v["number"], "baseline_arm": "pre-fix", "candidate_arm": "fix", "project": "cmd"},
                ),
                200,
                201,
            )
    if "gazebo-openamr" in envs:
        s.say("the Gazebo host is connected: create an experiment on it in the Studio to run the real simulation live")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--org", default="demo")
    ap.add_argument("--web", default="http://127.0.0.1:3000")
    ns = ap.parse_args()
    try:
        seed(Seeder(ns.api, ns.org))
    except httpx.HTTPError as e:
        sys.exit(f"cannot reach the API at {ns.api}: {e}. Start it with: uv run python scripts/dev_stack.py")
    print(
        f"\ndone. Open {ns.web}/settings, sign in as ada (admin), bob (engineer) or vic (viewer), workspace '{ns.org}'."
    )


if __name__ == "__main__":
    main()
