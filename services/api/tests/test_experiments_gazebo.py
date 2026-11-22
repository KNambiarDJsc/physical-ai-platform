"""SIM-006: the OpenAMRobot command-loss regression (#79 / PR #177) run BY THE PLATFORM on real Gazebo.

An experiment with a pre-fix arm and a fix arm is configured, approved by a second engineer, and executed through the
unchanged workflow worker; the simulation host (runtimes/sim-host, catalogs/gazebo-openamr.json) starts the repository's
own scenario scripts in WSL. Nothing is replayed and no telemetry or outcome comes from the test: the measurements are
Gazebo's world pose as the probe recorded it, the verdicts are the pinned engine's, and the test asserts only the
relation between them. Each run needs about 1.5 GB of memory and a few minutes, so this runs only where Gazebo is
installed (PAP_REQUIRE_GAZEBO=1 turns absence into a failure).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import add_member, as_user, make_org, ok
from pap_device_sdk.testing import run_sim_host
from test_experiments import BOB, VIC, configure_env, decide, trials_of, work_all
from test_twin_models import real

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "runtimes" / "sim-host" / "catalogs" / "gazebo-openamr.json"
ORG = "/api/v1/orgs/lab"
ADA = as_user("ada")
LIMIT_M = 0.15  # upstream's MAX_TRAVEL_AFTER_KILL_M (test_sim_cmd_vel_timeout_gazebo.py)
SWAPPED = {
    "ros2/src/openamrobot_gazebo/config/gz_bridge.yaml",
    "ros2/src/openamrobot_gazebo/launch/gz_simulator.launch.py",
}
DISTRO = os.environ.get("PAP_GAZEBO_DISTRO", "openmhs-ros")
READY_CHECK = "test -f ~/p79/install/setup.bash && test -f /opt/ros/jazzy/setup.bash"
STATUS_CHECK = "cd ~/p79/src/openamr-platform-sw && git status --porcelain; git rev-parse HEAD"
WSL_EXE = shutil.which("wsl.exe") or r"C:\Windows\System32\wsl.exe"

pytestmark = [pytest.mark.engine, pytest.mark.gazebo]


def gazebo_available() -> str | None:
    """Why Gazebo cannot run here, or None."""
    try:
        r = subprocess.run(
            [WSL_EXE, "-d", DISTRO, "-e", "bash", "-c", READY_CHECK],
            capture_output=True, timeout=120, check=False,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"WSL is not available: {e}"
    return None if r.returncode == 0 else f"no built openamr-platform-sw workspace in WSL distribution {DISTRO}"


@pytest.fixture(scope="module")
def gazebo_host(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    if os.environ.get("PAP_REQUIRE_GAZEBO") != "1" and os.environ.get("PAP_RUN_GAZEBO") != "1":
        pytest.skip(
            "real Gazebo runs are opt-in (minutes and ~1.5 GB each): set PAP_REQUIRE_GAZEBO=1 or PAP_RUN_GAZEBO=1"
        )
    why = gazebo_available()
    if why:
        if os.environ.get("PAP_REQUIRE_GAZEBO") == "1":
            pytest.fail(f"PAP_REQUIRE_GAZEBO=1 but {why}")
        pytest.skip(why)
    with run_sim_host(ROOT, CATALOG, work=tmp_path_factory.mktemp("gazebo-host")) as url:
        yield url


def checkout_status() -> str:
    r = subprocess.run(
        [WSL_EXE, "-d", DISTRO, "-e", "bash", "-c", STATUS_CHECK],
        capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    return r.stdout


def test_the_platform_runs_both_arms_on_gazebo_and_the_verdicts_follow_the_measurements(
    client: TestClient, gazebo_host: str, omhs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = checkout_status()
    configure_env(monkeypatch, gazebo_host, key="gazebo-sim", name="Gazebo (OpenAMRobot)")
    make_org(client, "ada", "lab", "robots")
    add_member(client, "ada", "lab", "bob", "engineer")
    add_member(client, "ada", "lab", "vic", "viewer")
    ok(client.post(f"{ORG}/environments", json={"config_key": "gazebo-sim"}, headers=ADA), 201)
    ok(client.post(f"{ORG}/environments/gazebo-sim/discover", headers=ADA))
    manifest, files = real()
    ok(
        client.post(
            f"{ORG}/projects/robots/twin/models",
            data={"manifest": json.dumps(manifest)},
            files=[("files", (Path(p).name, b, "application/octet-stream")) for p, b in files.items()],
            headers=ADA,
        ),
        201,
    )
    env = {e["slug"]: e for e in ok(client.get(f"{ORG}/simulation-environments", headers=VIC))}["gazebo-sim"]
    assert env["state"] == "ready" and env["simulator"]["kind"] == "gazebo"
    sc = env["scenarios"][0]
    spec = {
        "environment": "gazebo-sim",
        "simulator": env["simulator"],
        "scenario": {"id": sc["id"], "version": sc["version"], "definition_sha256": sc["definition_sha256"]},
        "model": {"project": "robots", "model": manifest["slug"], "version": 1},
        "software": [
            {
                "name": "openamr-platform-sw fix branch",
                "revision": before.split()[-1][:12] if before.split() else "unknown",
            },
            {"name": "openamr-platform-sw pre-fix wiring (origin/main)", "revision": "69847ab"},
        ],
        "repetitions": 1,
        "arms": [
            {"key": "pre-fix", "title": "Pre-fix wiring", "role": "baseline", "parameters": {"wiring": "main"}},
            {"key": "fix", "title": "Fix #79", "role": "candidate", "parameters": {"wiring": "fix"}},
        ],
        "limits": {"max_trials": 2, "max_wall_time_s": 1800},
        "observations": {
            "measurements": ["travel_after_kill_m", "driven_before_kill_m", "kill_sim_time_s"],
            "artifacts": ["recording", "bag-summary", "identity", "probe", "sim-log", "bag-log"],
            "recording": "recording",
            "summary": "bag-summary",
        },
        "contract": {
            "name": "command-loss-stop",
            "version": "1",
            "conditions": [
                {
                    "name": f"Travel after command loss is at most {LIMIT_M} m",
                    "measurement": "travel_after_kill_m",
                    "op": "le",
                    "value": LIMIT_M,
                }
            ],
        },
    }
    v = ok(
        client.post(f"{ORG}/experiments", json={"slug": "cmd-loss", "name": "Command loss stop #79"}, headers=ADA), 201
    )
    v = ok(client.post(f"{ORG}/experiments/cmd-loss/versions", json={"spec": spec}, headers=ADA), 201)
    rid = ok(
        client.post(f"{ORG}/experiments/cmd-loss/versions/1/requests", json={"note": "SIM-006"}, headers=ADA), 201
    )["id"]
    decide(client, rid, "approve", v["spec_sha256"], headers=BOB)

    from app.experiments.capture import capture_ready

    assert work_all() == ["succeeded", "succeeded"]  # two real Gazebo runs, one after the other
    assert capture_ready() == 2
    trials = {t["arm"]: t for t in trials_of(client, rid)}
    for arm, t in trials.items():
        travel = t["measurements"]["travel_after_kill_m"]
        assert t["verdict"] == ("SATISFIED" if travel <= LIMIT_M else "VIOLATED"), (arm, travel, t["verdict"])
        assert t["capture_state"] == "stored", t["capture_error"]
        assert {a["name"] for a in t["artifacts"] if a["state"] == "stored"} == {
            "recording", "bag-summary", "identity", "probe", "sim-log", "bag-log",
        }  # fmt: skip
        rec = ok(client.get(f"{ORG}/projects/robots/twin/recordings/{t['recording_id']}", headers=VIC))
        assert rec["run"]["id"] == t["run_id"] and rec["run"]["verdict"] == t["verdict"]
        assert rec["model"] == f"{manifest['slug']}@1"
        assert rec["summary"]["schema"] == "pap.ros.bag-summary/1"
        ident = rec["identity"]
        assert (
            ident["schema"] == "pap.ros.run-identity/1"
            and ident["launcher"]["wiring"] == t["host_run"]["identity"]["launcher"]["wiring"]
        )
        assert ident["software"]["repository"] == "openAMRobot/openamr-platform-sw"
    # The pre-fix arm says exactly how it differs from the commit; the fix arm ran a clean checkout.
    pre, fix = trials["pre-fix"]["host_run"]["identity"], trials["fix"]["host_run"]["identity"]
    assert pre["software"]["tree_dirty"] is True and set(pre["software"]["changed_files"]) == SWAPPED
    assert fix["software"]["tree_dirty"] is False and fix["software"]["changed_files"] == []
    assert pre["software"]["commit"] == fix["software"]["commit"]
    # The checkout is exactly as it was before the runs.
    assert checkout_status() == before
    # Individual contract violations, not a release verdict: no statistic is made from one run per arm.
    d = ok(client.get(f"{ORG}/experiment-requests/{rid}", headers=VIC))
    for a in d["arms"]:
        assert a["trials"] == 1 and not {"mean", "p_value", "ci95", "difference", "regression"} & set(a)
    print(json.dumps({arm: [t["measurements"], t["verdict"]] for arm, t in trials.items()}))
