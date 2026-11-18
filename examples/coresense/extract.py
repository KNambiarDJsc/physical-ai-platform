"""Real robot evidence: the CoreSense Inspection Testbed ROSbag Dataset as platform source files (Milestone B).

    uv run python examples/coresense/extract.py /path/to/coresense/bags --out examples/coresense/data

Source: three Crazyflie drones flown under Aerostack2 with OptiTrack motion capture (Zenodo 10.5281/zenodo.23243295,
CC BY 4.0, Garcia Patino Lenza, Universidad Politecnica de Madrid). Real flights in a test facility; the failures in
the panel/double-failure bags were induced by the experimenters.

One CSV row per GoTo goal of each drone, read with the pinned OpenMHS commit's own rosbag2 reader
(``.engine/src-<commit>/python/openmhs/importers``, used read-only, never modified):

- ``robot_status``: the terminal status the drone's own ``GoToBehavior`` action reported (SUCCEEDED/CANCELED/ABORTED),
  blank if the goal never reached one. This is the robot's claim.
- ``target_x/target_y``: the waypoint, joined from the swarm knowledge base (``goto_N to wp_K``, nearest fact within
  300 ms of the goal start, as the OpenMHS verifier does). Blank when no waypoint can be joined.
- ``pose_*``: the motion-capture pose sample nearest the claim time, only if within 50 ms of it; ``dx_m/dy_m`` are its
  offsets from the waypoint. Blank when there is no such sample. Nothing is interpolated or estimated.

What this file cannot say: the dataset names no software revision (so there is no baseline-vs-candidate *release*,
only flight conditions), publishes no Aerostack2 configuration (so the 0.20 m arrival tolerance in mapping.json is the
Aerostack2 default, an assumption), and the motion-capture pose also feeds the controller (the reference is not fully
independent of what the robot itself used). Times are the recorder's receipt times on one host clock (assumed).
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = json.loads((ROOT / "engine.lock.json").read_text(encoding="utf-8"))
OPENMHS_PY = ROOT / ".engine" / f"src-{LOCK['commit']}" / "python"
WINDOW_NS = 50_000_000
LINK_NS = 300_000_000
COLUMNS = [
    "episode_id", "drone", "condition", "goal_id", "waypoint", "start_time", "end_time", "robot_status",
    "target_x", "target_y", "pose_time", "pose_x", "pose_y", "pose_z", "dx_m", "dy_m", "pose_gap_ms", "data_origin",
]  # fmt: skip


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def rows_for(bag_dir: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    from openmhs.importers import coresense_aerostack2 as imp
    from openmhs.importers import coresense_verify as cv

    bag = imp.Bag(bag_dir)
    counts = {"goals": 0, "no_terminal_status": 0, "no_waypoint": 0, "no_pose_in_window": 0}
    try:
        cond = imp.condition_of(bag_dir)
        wp = cv.waypoints(bag)
        rows = []
        for drone in bag.drones():
            poses = cv.load_poses(bag, drone)
            times = [p[0] for p in poses]
            links = cv.goto_links(bag, drone)
            for g in imp.goals(bag, drone, "GoTo"):
                if not g["start"]:
                    continue
                counts["goals"] += 1
                row = dict.fromkeys(COLUMNS, "")
                row.update(
                    episode_id=f"{cond}/{drone}/goto/{g['goal_id'].replace('-', '')[:12]}",
                    drone=f"crazyflie/{drone}",
                    condition=cond,
                    goal_id=g["goal_id"],
                    start_time=imp.rfc(g["start"]),
                    end_time=imp.rfc(g["end"] or g["start"]),
                    robot_status=g["status"] or "",
                    data_origin="physical-test-flight",
                )
                if not g["status"]:
                    counts["no_terminal_status"] += 1
                best = min(links, key=lambda li: abs(li[0] - g["start"]), default=None)
                target = None
                if best and abs(best[0] - g["start"]) <= LINK_NS and len(wp.get(best[1], {})) == 2:
                    target = wp[best[1]]
                    row.update(waypoint=best[1], target_x=f"{target['x']:.4f}", target_y=f"{target['y']:.4f}")
                else:
                    counts["no_waypoint"] += 1
                if g["end"]:
                    i = bisect.bisect_left(times, g["end"])
                    near = [j for j in (i - 1, i) if 0 <= j < len(poses)]
                    j = min(near, key=lambda k: abs(times[k] - g["end"]), default=None)
                    if j is not None and abs(times[j] - g["end"]) <= WINDOW_NS:
                        t, x, y, z = poses[j]
                        row.update(pose_time=imp.rfc(t), pose_x=f"{x:.4f}", pose_y=f"{y:.4f}", pose_z=f"{z:.4f}",
                                   pose_gap_ms=f"{(t - g['end']) / 1e6:.1f}")  # fmt: skip
                        if target:
                            row.update(dx_m=f"{x - target['x']:.4f}", dy_m=f"{y - target['y']:.4f}")
                    else:
                        counts["no_pose_in_window"] += 1
                rows.append(row)
        return rows, counts
    finally:
        bag.con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bags", type=Path, help="directory holding the rosbag2_real_paths_2_OK_<condition> folders")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "data")
    ns = ap.parse_args()
    if not OPENMHS_PY.is_dir():
        print(f"pinned OpenMHS source not found at {OPENMHS_PY}: bash scripts/build-openmhs.sh", file=sys.stderr)
        return 2
    sys.path.insert(0, str(OPENMHS_PY))
    ns.out.mkdir(parents=True, exist_ok=True)
    provenance = {"dataset": "10.5281/zenodo.23243295", "license": "CC-BY-4.0", "openmhs_commit": LOCK["commit"],
                  "pose_window_ms": WINDOW_NS / 1e6, "bags": {}}  # fmt: skip
    for bag_dir in sorted(p for p in ns.bags.iterdir() if p.name.startswith("rosbag2_real_paths_")):
        rows, counts = rows_for(bag_dir)
        cond = rows[0]["condition"] if rows else bag_dir.name
        out = ns.out / f"{cond}.csv"
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        db3 = next(bag_dir.glob("*.db3"))
        provenance["bags"][bag_dir.name] = {"db3": db3.name, "db3_sha256": sha256(db3), "csv": out.name,
                                            "csv_sha256": sha256(out), "rows": len(rows), **counts}  # fmt: skip
        print(f"{bag_dir.name}: {len(rows)} GoTo goals -> {out.name} {counts}")
    (ns.out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
