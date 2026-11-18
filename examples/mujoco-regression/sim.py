"""Controlled regression experiment (Milestone C): a planar two-link arm reaching task in MuJoCo, CPU only, headless.

    uv run python examples/mujoco-regression/sim.py pilot          # pilot seeds: runtime, memory, variability
    uv run python examples/mujoco-regression/sim.py run --n 150    # held-out groups A, B, C -> data/*.csv

Everything an episode says comes from the simulation: nothing is drawn or edited after the fact.

The robot's own view (what it REPORTS):
    joint encoders, quantized to 4096 counts per revolution, through its NOMINAL kinematic model (links 0.300 and
    0.250 m). It declares success when that estimate is within 2 cm of the target and the joints are still for 0.1 s,
    and reports a timeout if that never happens within 3 s.
The independent measurement (what the platform VERIFIES against):
    the simulator's ground-truth fingertip position at the moment of the robot's report. The real links are 0.303 and
    0.247 m, a calibration error the robot does not know about, identical in every group.

Groups (configuration in GROUPS, seeds in SEEDS; both fixed before the held-out run, see PREREGISTRATION.md):
    A  baseline controller, 10 ms command latency
    B  the same controller with 50 ms command latency (the injected regression), on the SAME seeds as A
    C  the baseline controller again, on INDEPENDENT seeds (no-change control)
    D  the same controller with 20 ms command latency (secondary regression chosen on the pilot), SAME seeds as A
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
EPOCH_S = 1_767_225_600  # 2026-01-01T00:00:00Z: the simulated clock starts here; episodes are 10 s apart
MEMORY_BUDGET_MB = 400

MJCF = """
<mujoco model="planar-arm">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="upper" pos="0 0 0">
      <joint name="shoulder" type="hinge" axis="0 0 1" damping="0.05" armature="0.01"/>
      <geom type="capsule" fromto="0 0 0 {l1} 0 0" size="0.02" mass="1.0"/>
      <body name="fore" pos="{l1} 0 0">
        <joint name="elbow" type="hinge" axis="0 0 1" damping="0.05" armature="0.01"/>
        <geom type="capsule" fromto="0 0 0 {l2} 0 0" size="0.015" mass="0.6"/>
        <site name="tip" pos="{l2} 0 0" size="0.005"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor joint="shoulder" ctrlrange="-4 4" ctrllimited="true"/>
    <motor joint="elbow" ctrlrange="-4 4" ctrllimited="true"/>
  </actuator>
</mujoco>
"""


@dataclass(frozen=True)
class Config:
    """Everything that defines a group. Its SHA-256 is recorded with every rollout."""

    true_links: tuple[float, float] = (0.303, 0.247)
    nominal_links: tuple[float, float] = (0.300, 0.250)
    encoder_counts: int = 4096
    control_hz: int = 100
    kp: tuple[float, float] = (30.0, 15.0)
    kd: tuple[float, float] = (3.0, 1.2)
    move_s: float = 1.0
    timeout_s: float = 3.0
    success_tol_m: float = 0.02
    still_rad_s: float = 0.2  # above one encoder count per control period (0.153 rad/s); 0.05 never held (pilot)
    still_steps: int = 10
    latency_ms: int = 10

    def sha256(self) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


GROUPS = {
    "A": Config(latency_ms=10),  # baseline
    "B": Config(latency_ms=50),  # primary injected regression, declared before the pilot
    "C": Config(latency_ms=10),  # no-change control: the baseline on independent seeds
    "D": Config(latency_ms=20),  # secondary regression, chosen on the pilot: the one step between baseline and collapse
}
SEEDS = {
    "pilot": range(900_000, 900_030),
    "A": range(1_000, 2_000),
    "B": range(1_000, 2_000),  # same initial conditions as A (paired)
    "C": range(5_000, 6_000),  # independent initial conditions from the same distribution
    "D": range(1_000, 2_000),  # same initial conditions as A (paired)
}


def ik(x: float, y: float, links: tuple[float, float]) -> tuple[float, float]:
    """Elbow-down inverse kinematics of the nominal model."""
    l1, l2 = links
    c2 = (x * x + y * y - l1 * l1 - l2 * l2) / (2 * l1 * l2)
    q2 = math.acos(max(-1.0, min(1.0, c2)))
    q1 = math.atan2(y, x) - math.atan2(l2 * math.sin(q2), l1 + l2 * math.cos(q2))
    return q1, q2


def fk(q: np.ndarray, links: tuple[float, float]) -> np.ndarray:
    l1, l2 = links
    return np.array(
        [l1 * math.cos(q[0]) + l2 * math.cos(q[0] + q[1]), l1 * math.sin(q[0]) + l2 * math.sin(q[0] + q[1])]
    )


def initial_conditions(seed: int, cfg: Config) -> tuple[np.ndarray, np.ndarray]:
    """Start pose and target from the seed alone, so the same seed gives the same episode setup in every group."""
    rng = np.random.default_rng(seed)
    q0 = np.array([rng.uniform(-math.pi / 2, math.pi / 2), rng.uniform(0.3, 2.2)])
    r = rng.uniform(0.18, 0.50)
    a = rng.uniform(-2.4, 2.4)
    return q0, np.array([r * math.cos(a), r * math.sin(a)])


def episode(seed: int, cfg: Config, model: mujoco.MjModel) -> dict[str, Any]:
    data = mujoco.MjData(model)
    q0, target = initial_conditions(seed, cfg)
    data.qpos[:] = q0
    mujoco.mj_forward(model, data)
    q_goal = np.array(ik(float(target[0]), float(target[1]), cfg.nominal_links))
    per_ctrl = round(1.0 / (cfg.control_hz * model.opt.timestep))
    delay = max(0, round(cfg.latency_ms / 1000 * cfg.control_hz))
    tick = 2 * math.pi / cfg.encoder_counts
    queue: list[np.ndarray] = [np.zeros(2)] * delay
    prev = np.round(q0 / tick) * tick
    still = 0
    steps = round(cfg.timeout_s * cfg.control_hz)
    report, t_report = "timeout", cfg.timeout_s
    for k in range(steps):
        t = k / cfg.control_hz
        q_meas = np.round(data.qpos / tick) * tick  # what the encoders say
        qd_meas = (q_meas - prev) * cfg.control_hz
        prev = q_meas
        s = min(1.0, t / cfg.move_s)
        s = s * s * (3 - 2 * s)  # smooth step from start to goal
        q_des = q0 + s * (q_goal - q0)
        tau = np.array(cfg.kp) * (q_des - q_meas) - np.array(cfg.kd) * qd_meas
        queue.append(tau)
        data.ctrl[:] = queue.pop(0)  # the command applied now was computed `delay` control periods ago
        est = fk(q_meas, cfg.nominal_links)
        near = float(np.linalg.norm(est - target)) <= cfg.success_tol_m
        still = still + 1 if near and float(np.max(np.abs(qd_meas))) <= cfg.still_rad_s else 0
        if still >= cfg.still_steps and t >= cfg.move_s:
            report, t_report = "succeeded", t
            break
        for _ in range(per_ctrl):
            mujoco.mj_step(model, data)
    tip = data.site("tip").xpos[:2].copy()  # ground truth at the moment of the report
    return {
        "seed": seed,
        "target_x": float(target[0]),
        "target_y": float(target[1]),
        "reported": report,
        "report_s": t_report,
        "tip_x": float(tip[0]),
        "tip_y": float(tip[1]),
        "tip_error_m": float(np.linalg.norm(tip - target)),
        "robot_estimated_error_m": float(np.linalg.norm(fk(prev, cfg.nominal_links) - target)),
    }


def peak_rss_mb() -> float:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (n, ctypes.c_size_t)
                for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                          "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")
            ]  # fmt: skip

        # Typed handles: without restype/argtypes the pseudo-handle was truncated and the call silently read 0 MB
        # (found in the pilot), which would have disabled the budget check.
        kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        c = Counters()
        c.cb = ctypes.sizeof(c)
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return c.PeakWorkingSetSize / 2**20
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 2**20 if sys.platform == "darwin" else rss / 1024


def rfc(seconds: float) -> str:
    whole = math.floor(seconds)
    ms = round((seconds - whole) * 1000)
    if ms == 1000:
        whole, ms = whole + 1, 0
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(whole)) + f".{ms:03d}Z"


def rollouts(group: str, seeds: range, offset: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    cfg = GROUPS.get(group, GROUPS["A"])
    model = mujoco.MjModel.from_xml_string(MJCF.format(l1=cfg.true_links[0], l2=cfg.true_links[1]))
    rows, started = [], time.perf_counter()
    for i, seed in enumerate(seeds):
        e = episode(seed, cfg, model)
        start = EPOCH_S + (offset + i) * 10
        rows.append({
            "episode_id": f"{group}-{seed}", "group": group, "scenario": f"ic-{seed}", "seed": str(seed),
            "start_time": rfc(start), "end_time": rfc(start + e["report_s"]), "robot_status": e["reported"],
            "target_x": f"{e['target_x']:.5f}", "target_y": f"{e['target_y']:.5f}",
            "tip_x": f"{e['tip_x']:.5f}", "tip_y": f"{e['tip_y']:.5f}", "tip_error_m": f"{e['tip_error_m']:.5f}",
            "robot_estimated_error_m": f"{e['robot_estimated_error_m']:.5f}", "data_origin": "simulated",
        })  # fmt: skip
        if peak_rss_mb() > MEMORY_BUDGET_MB:
            raise SystemExit(f"peak memory {peak_rss_mb():.0f} MB exceeds the {MEMORY_BUDGET_MB} MB budget: stopped")
    wall = time.perf_counter() - started
    meta: dict[str, Any] = {"group": group, "config": asdict(cfg), "config_sha256": cfg.sha256()}
    meta["seeds"] = [seeds.start, seeds.stop]
    meta.update(episodes=len(rows), wall_s=round(wall, 3), peak_rss_mb=round(peak_rss_mb(), 1))
    return rows, meta


COLUMNS = ["episode_id", "group", "scenario", "seed", "start_time", "end_time", "robot_status", "target_x", "target_y",
           "tip_x", "tip_y", "tip_error_m", "robot_estimated_error_m", "data_origin"]  # fmt: skip


def write(rows: list[dict[str, str]], path: Path) -> str:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def environment() -> dict[str, Any]:
    return {"mujoco": mujoco.__version__, "numpy": np.__version__, "python": platform.python_version(),
            "machine": platform.machine(), "system": platform.system(), "cpu_count": os.cpu_count()}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pilot")
    run = sub.add_parser("run")
    run.add_argument("--n", type=int, required=True, help="episodes per group, fixed in PREREGISTRATION.md")
    run.add_argument("--out", type=Path, default=HERE / "data")
    ns = ap.parse_args()
    if ns.cmd == "pilot":
        out = {"environment": environment(), "groups": {}}
        for g in ("A", "B"):
            rows, meta = rollouts(g, SEEDS["pilot"], 0)
            failed = sum(r["robot_status"] != "succeeded" for r in rows)
            off = sum(float(r["tip_error_m"]) > GROUPS[g].success_tol_m for r in rows)
            meta.update(reported_not_succeeded=failed, tip_outside_tol=off)
            out["groups"][g] = meta
        (HERE / "pilot.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(out, indent=2))
        return 0
    ns.out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"environment": environment(), "n_per_group": ns.n, "groups": {}}
    for i, g in enumerate(("A", "B", "C", "D")):
        seeds = range(SEEDS[g].start, SEEDS[g].start + ns.n)
        rows, meta = rollouts(g, seeds, i * 10_000)
        meta["csv"] = f"{g}.csv"
        meta["csv_sha256"] = write(rows, ns.out / f"{g}.csv")
        manifest["groups"][g] = meta
    (ns.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
