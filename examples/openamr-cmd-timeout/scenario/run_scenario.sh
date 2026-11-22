#!/usr/bin/env bash
# One run of upstream's command-timeout scenario (openamr-platform-sw issue #79 / PR #177), recorded for the platform:
# a headless Gazebo simulation, the base driven at 0.2 m/s from a `ros2 topic pub` publisher, the publisher killed after
# 4 s of simulation time, the base's travel measured from Gazebo's world pose for 5 s more. It also records an MCAP bag
# of the relevant topics and writes the run's identity (software commit and whether the tree was dirty, configuration,
# ROS and RMW versions, host) beside the bag.
#
# THIS IS NOT PART OF THE PLATFORM. The platform never starts it, never publishes to a ROS topic, never touches a
# controller: it only reads what this leaves behind. Run it yourself inside WSL (needs the built openamr-platform-sw
# workspace, ~1.5 GB of RAM for a few minutes at real-time factor 0.1).
#
#   bash run_scenario.sh <label> <out-dir>        e.g.  bash run_scenario.sh fix /mnt/d/runs/fix_1
#   WS=~/p79 (workspace with install/)   ROS_DOMAIN_ID=79   GZ_PARTITION=p79
set -u
LABEL="${1:?label (main or fix)}"; OUT="${2:?out dir}"
WS="${WS:-$HOME/p79}"; UP="$WS/src/openamr-platform-sw"; HERE="$(cd "$(dirname "$0")" && pwd)"
set +u; source /opt/ros/jazzy/setup.bash; source "$WS/install/setup.bash"; set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-79}" GZ_PARTITION="${GZ_PARTITION:-p79}"
mkdir -p "$OUT"; RUN_ID="${LABEL}_$(date -u +%Y%m%dT%H%M%SZ)"

python3 - "$RUN_ID" "$LABEL" "$UP" "$OUT" <<'PY'
import hashlib, json, os, socket, subprocess, sys, datetime
run_id, label, up, out = sys.argv[1:5]
def git(*a):
    return subprocess.run(["git", "-C", up, *a], capture_output=True, text=True, check=False).stdout.strip()
cfg = os.path.join(up, "ros2/src/openamrobot_gazebo/config/sim_cmd_vel_timeout.yaml")
ident = {
    "schema": "pap.ros.run-identity/1", "run_id": run_id, "arm": label,
    "scenario": {"name": "command_loss_stop", "procedure": "publisher_kill", "commanded_m_per_s": 0.2,
                 "kill_after_sim_s": 4.0, "watch_sim_s": 5.0, "upstream_test": "test_sim_cmd_vel_timeout_gazebo.py"},
    "software": {"repository": "openAMRobot/openamr-platform-sw", "commit": git("rev-parse", "HEAD"),
                 "branch": git("branch", "--show-current"), "tree_dirty": bool(git("status", "--porcelain")),
                 "origin_main": git("rev-parse", "origin/main"),
                 # A dirty tree is described, not hidden: which files differ from the commit, and a digest of the diff.
                 "changed_files": sorted(git("diff", "--name-only").split()),
                 "diff_sha256": hashlib.sha256(git("diff").encode()).hexdigest() if git("diff") else None,
                 "note": os.environ.get("PAP_IDENTITY_NOTE")},
    "configuration": {"launch": "openamrobot_gazebo gz_simulator.launch.py gui:=false",
                      "sim_cmd_vel_timeout.yaml": open(cfg, encoding="utf-8").read() if os.path.exists(cfg) else None},
    "environment": {"ros_distro": os.environ.get("ROS_DISTRO"), "rmw": os.environ.get("RMW_IMPLEMENTATION", "default"),
                    "ros_domain_id": os.environ.get("ROS_DOMAIN_ID"), "gz_partition": os.environ.get("GZ_PARTITION"),
                    "host": socket.gethostname()},
    "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
json.dump(ident, open(os.path.join(out, "pap-run-identity.json"), "w"), indent=1, sort_keys=True)
PY

ros2 launch openamrobot_gazebo gz_simulator.launch.py gui:=false >"$OUT/sim.log" 2>&1 </dev/null &
SIM=$!
for _ in $(seq 1 120); do ros2 topic list 2>/dev/null | grep -q '^/clock$' && break; sleep 1; done
sleep 10   # the base and its controllers finish starting
# Its own session, so the stop signal below reaches the recorder itself.
setsid ros2 bag record -s mcap -o "$OUT/bag" /clock /cmd_vel /sim/base_cmd_vel /odom /tf /joint_states >"$OUT/bag.log" 2>&1 </dev/null &
BAG=$!
sleep 4
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2}}" >/dev/null 2>&1 </dev/null &
PUB=$!
timeout 240 python3 "$HERE/pose_probe.py" "$PUB" "$OUT/probe.json" 2>&1 | tail -8
# SIGTERM, not SIGINT: a background job of a non-interactive shell has SIGINT ignored, so the recorder would never close
# the MCAP or write metadata.yaml. SIGTERM makes it finalise.
kill -TERM -- "-$BAG" 2>/dev/null
for _ in $(seq 1 30); do [ -f "$OUT/bag/metadata.yaml" ] && break; sleep 1; done
kill -INT "$SIM" 2>/dev/null; sleep 5
for p in "gz sim" parameter_bridge robot_state_publisher joint_state_publisher sim_cmd_vel_timeout "topic pub"; do pkill -9 -f "$p" 2>/dev/null; done
echo "run: $RUN_ID  out: $OUT"
