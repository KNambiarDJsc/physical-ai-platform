"""The simulation host's command for the OpenAMRobot command-loss scenario (#79 / PR #177): one real Gazebo run in WSL.

    python platform_run.py <run_dir> <params.json>          (params: {"wiring": "main" | "fix"})

The host runs this as an argument list from its catalog; nothing a caller sends is ever part of a command. This script
only starts the repository's own scenario scripts in WSL (``run_scenario.sh`` for the fix, ``run_main.sh`` for the
pre-fix wiring), then reads what they left behind and writes the result file the host contract asks for. It invents
no measurement: the numbers are the probe's, taken from Gazebo's own world pose, and every file is the run's own.

Before anything starts it checks that the machine can take the run (free memory on Windows and in the WSL VM, free disk,
no simulation already running) and refuses cleanly, starting nothing, when it cannot. Afterwards it verifies that the
local checkout is exactly as it was (``run_main.sh`` restores the two wiring files it swaps) and restores them itself
if the run was interrupted.

Exit codes: 0 result written; 2 bad parameters; 3 refused (resources); 4 the run failed; 5 the checkout needed repair.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

DISTRO = os.environ.get("PAP_GAZEBO_DISTRO", "openmhs-ros")
WS = os.environ.get("PAP_GAZEBO_WS", "~/p79")  # the built openamr-platform-sw workspace inside the distro
# The run needs about 1.5 GB inside WSL (checked there). Windows needs a floor of its own: once WSL has grown, the
# memory it holds stays available to the next run inside the VM, so Windows "free" understates what a run can use.
MIN_FREE_WIN_MB = int(os.environ.get("PAP_GAZEBO_MIN_FREE_MB", "1000"))
MIN_FREE_WSL_MB = int(os.environ.get("PAP_GAZEBO_MIN_FREE_WSL_MB", "1500"))
MIN_FREE_DISK_MB = int(os.environ.get("PAP_GAZEBO_MIN_FREE_DISK_MB", "1024"))
RUN_TIMEOUT_S = int(os.environ.get("PAP_GAZEBO_RUN_TIMEOUT_S", "840"))
SWAPPED = (
    "ros2/src/openamrobot_gazebo/config/gz_bridge.yaml",
    "ros2/src/openamrobot_gazebo/launch/gz_simulator.launch.py",
)
HERE = Path(__file__).resolve().parent
WSL_EXE = shutil.which("wsl.exe") or r"C:\Windows\System32\wsl.exe"
OBSERVER_SRC = HERE.parents[2] / "runtimes" / "ros-observer" / "src"
ARTIFACTS = {  # name in the catalog -> path under the run directory
    "bag-summary": "gazebo/bag-summary.json",
    "identity": "gazebo/pap-run-identity.json",
    "probe": "gazebo/probe.json",
    "sim-log": "gazebo/sim.log",
    "bag-log": "gazebo/bag.log",
}


class Refused(Exception):
    """The run was not started, and why."""


class Failed(Exception):
    pass


def wsl(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [WSL_EXE, "-d", DISTRO, "-e", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def wsl_path(p: Path) -> str:
    r = wsl(["wslpath", "-a", str(p)])
    if r.returncode != 0 or not r.stdout.strip():
        raise Failed(f"cannot translate {p} for WSL: {r.stderr.strip()}")
    return r.stdout.strip()


def windows_free_mb() -> int:
    class MemStatus(ctypes.Structure):
        _fields_ = [  # noqa: RUF012 - ctypes reads this class attribute
            ("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total_phys", ctypes.c_ulonglong),
            ("avail_phys", ctypes.c_ulonglong), ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
            ("avail_ext", ctypes.c_ulonglong),
        ]  # fmt: skip

    s = MemStatus()
    s.length = ctypes.sizeof(MemStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))  # type: ignore[attr-defined]
    return int(s.avail_phys // (1024 * 1024))


def preflight(run_dir: Path) -> dict[str, int]:
    """Refuse, starting nothing, unless this machine can take one more run."""
    win = windows_free_mb()
    if win < MIN_FREE_WIN_MB:
        raise Refused(
            f"only {win} MB of memory is free on this machine; it needs {MIN_FREE_WIN_MB} MB during a Gazebo run. "
            "Close other programs and run again."
        )
    disk = shutil.disk_usage(run_dir).free // (1024 * 1024)
    if disk < MIN_FREE_DISK_MB:
        raise Refused(f"only {disk} MB of disk is free where the run is kept; it needs {MIN_FREE_DISK_MB} MB.")
    r = wsl(["bash", "-c", "free -m | awk '/^Mem:/ {print $7}'; pgrep -fc '[g]z sim' || true"], timeout=120)
    lines = r.stdout.split()
    if r.returncode != 0 or not lines:
        raise Refused(f"the WSL distribution {DISTRO} did not answer: {r.stderr.strip()[:200]}")
    wsl_free = int(lines[0])
    if wsl_free < MIN_FREE_WSL_MB:
        raise Refused(
            f"only {wsl_free} MB of memory is free inside WSL; a Gazebo run needs about {MIN_FREE_WSL_MB} MB."
        )
    if len(lines) > 1 and int(lines[1]) > 0:
        raise Refused(
            "a Gazebo simulation is already running in WSL; runs are sequential, so this one was not started."
        )
    dirty = checkout_state()
    if dirty:
        raise Refused(
            "the openamr-platform-sw checkout in WSL has local changes, so a run would not be of a known revision: "
            + " ".join(dirty.split()[:6])
        )
    return {"windows_free_mb": win, "wsl_free_mb": wsl_free, "disk_free_mb": int(disk)}


def checkout_state() -> str:
    r = wsl(["bash", "-c", f"cd {WS}/src/openamr-platform-sw && git status --porcelain"], timeout=60)
    return r.stdout.strip()


def repair_checkout() -> bool:
    """The scripts restore the two swapped files themselves. If the run was cut short they may not have: put back
    those two files from the commit the checkout is on (it was clean before, or the run was refused)."""
    if not checkout_state():
        return False
    files = " ".join(SWAPPED)
    wsl(["bash", "-c", f"cd {WS}/src/openamr-platform-sw && git checkout -- {files}"], timeout=60)
    if checkout_state():
        raise Failed(
            "the openamr-platform-sw checkout is not clean after the run and could not be restored; check it by hand"
        )
    return True


def read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def collect(run_dir: Path, out: Path) -> dict[str, Any]:
    """The host's result from what the run left in ``out``. Raises Failed if anything the contract needs is missing."""
    probe_file = out / "probe.json"
    if not probe_file.is_file():
        raise Failed("the run left no probe.json: there is no measurement to report")
    res = read_json(probe_file).get("result") or {}
    names = {
        "travel_after_kill_m": "travel_after_kill_m",
        "driven_before_kill_m": "driven_before_kill_m",
        "kill_sim_time_s": "t_kill_sim",
    }
    measurements: dict[str, float] = {}
    for key, src in names.items():
        v = res.get(src)
        if not isinstance(v, int | float) or isinstance(v, bool) or not math.isfinite(v):
            raise Failed(f"the probe's result has no finite {src}")
        measurements[key] = float(v)
    bags = sorted((out / "bag").glob("*.mcap"))
    if len(bags) != 1:
        raise Failed(f"expected one MCAP in the bag, found {len(bags)}")
    ident_file = out / "pap-run-identity.json"
    if not ident_file.is_file():
        raise Failed("the run left no identity file")
    artifacts = {"recording": bags[0].relative_to(run_dir).as_posix()}
    for name, rel in ARTIFACTS.items():
        if (run_dir / rel).is_file():
            artifacts[name] = rel
    return {"measurements": measurements, "artifacts": artifacts, "identity": read_json(ident_file)}


def main() -> int:
    run_dir, params_file = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    wiring = read_json(params_file).get("wiring")
    if wiring not in ("main", "fix"):
        print(f"wiring must be 'main' or 'fix', not {wiring!r}", file=sys.stderr)
        return 2
    out = run_dir / "gazebo"
    try:
        free = preflight(run_dir)
    except Refused as e:
        print(f"refused, nothing was started: {e}", file=sys.stderr)
        return 3
    print(f"resources before the run: {free}", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    script_dir, out_wsl = wsl_path(HERE), wsl_path(out)
    cmd = (
        f"bash {script_dir}/run_main.sh {out_wsl}"
        if wiring == "main"
        else f"bash {script_dir}/run_scenario.sh fix {out_wsl}"
    )
    try:
        r = wsl(["bash", "-c", f"export WS={WS}; {cmd}"], timeout=RUN_TIMEOUT_S)
        print(r.stdout[-3000:], flush=True)
        if r.stderr.strip():
            print(r.stderr[-1500:], file=sys.stderr)
        code = r.returncode
    except subprocess.TimeoutExpired:
        wsl(
            [
                "bash",
                "-c",
                "for p in 'gz sim' parameter_bridge ros2 'topic pub'; do pkill -9 -f \"$p\" 2>/dev/null; done",
            ],
            timeout=60,
        )
        code = -1
        print(f"the run did not finish within {RUN_TIMEOUT_S} s and was stopped", file=sys.stderr)
    repaired = repair_checkout()
    if repaired:
        print("the checkout had to be restored after the run", file=sys.stderr)
    if code != 0:
        print(f"the scenario script exited {code}", file=sys.stderr)
        return 5 if repaired else 4
    # The bag summary is the observer's own, computed from the bag and the identity (needs ROS, so inside WSL).
    summary = out / "bag-summary.json"
    src = wsl_path(OBSERVER_SRC)
    s = wsl(
        [
            "bash",
            "-c",
            f"source /opt/ros/jazzy/setup.bash && PYTHONPATH={src}:$PYTHONPATH python3 -m pap_ros_observer bag-summary "
            f"{out_wsl}/bag --identity {out_wsl}/pap-run-identity.json",
        ],
        timeout=300,
    )
    if s.returncode != 0 or not s.stdout.strip():
        print(f"the bag summary could not be made: {s.stderr.strip()[-400:]}", file=sys.stderr)
        return 4
    summary.write_text(s.stdout, encoding="utf-8")
    try:
        result = collect(run_dir, out)
    except Failed as e:
        print(str(e), file=sys.stderr)
        return 4
    result["identity"] = {
        **result["identity"],
        "preflight": free,
        "launcher": {"wiring": wiring, "checkout_repaired": repaired},
    }
    (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
