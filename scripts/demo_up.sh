#!/usr/bin/env bash
# One command to a presentable stack: web :3000, API :8000, the virtual lab, a recorded ROS observer, the self-test
# simulation host and (if the WSL workspace is present) the real Gazebo host, seeded with the demonstration workspace.
#
#   bash scripts/demo_up.sh            # start (state in var/demo), seed, print how to sign in
#   touch var/demo/stop                # stop everything cleanly
#
# Needs the web app built once: npm --prefix apps/web run build
set -euo pipefail
cd "$(dirname "$0")/.."
STATE="${PAP_DEMO_STATE:-var/demo}"
mkdir -p "$STATE"
rm -f "$STATE/ready.json" "$STATE/stop"
test -d apps/web/.next || { echo "build the web app first: npm --prefix apps/web run build" >&2; exit 1; }

LAB=8865 ROS=8866 GAZ=8867 SELF=8868
ENVS=$(uv run python - <<'PY'
import json
print(json.dumps([
 {"key":"virtual-lab","name":"Virtual laboratory","kind":"simulated","endpoint":"http://127.0.0.1:8865","description":"Simulated syringe pump and analytical balance (LabThings). No hardware."},
 {"key":"openamr-recorded","name":"OpenAMRobot upperbody (RECORDED snapshot, not live)","kind":"simulated","endpoint":"http://127.0.0.1:8866","description":"Observations recorded from a real ROS 2 graph and replayed unchanged."},
 {"key":"selftest-sim","name":"Self-test simulation host","kind":"simulated","endpoint":"http://127.0.0.1:8868","description":"A small kinematic base model. Not a simulator and not Gazebo: it exercises the experiment pipeline."},
 {"key":"gazebo-openamr","name":"Gazebo: OpenAMRobot (WSL)","kind":"simulated","endpoint":"http://127.0.0.1:8867","description":"Real headless Gazebo runs of openamr-platform-sw in WSL. One at a time, about 1.5 GB and a few minutes each."},
]))
PY
)
export PAP_ENVIRONMENTS="$ENVS"

# The Gazebo host: only when the WSL workspace exists (it refuses a run when memory is short or Gazebo is busy).
if wsl.exe -d openmhs-ros -e bash -c 'test -f ~/p79/install/setup.bash' >/dev/null 2>&1; then
  (uv run --quiet --project runtimes/sim-host python -m pap_sim_host.server \
     --catalog runtimes/sim-host/catalogs/gazebo-openamr.json --port "$GAZ" --work "$STATE/sim-host-gazebo" \
     >"$STATE/gazebo-host.log" 2>&1 &)
  echo "gazebo host starting on :$GAZ"
else
  echo "WSL workspace not found: the live Gazebo environment will show as not answering (recorded runs still work)"
fi

(uv run python scripts/dev_stack.py --api-port 8000 --web-port 3000 --lab-port "$LAB" --sim-port "$SELF" \
   --ros-replay runtimes/ros-observer/tests/fixtures/openamr-upperbody-mock.snapshot.json --ros-replay-port "$ROS" \
   --state-dir "$STATE" --ready-file "$STATE/ready.json" --stop-file "$STATE/stop" >"$STATE/stack.log" 2>&1 &)

for _ in $(seq 1 180); do [ -f "$STATE/ready.json" ] && break; sleep 2; done
[ -f "$STATE/ready.json" ] || { echo "stack did not start; see $STATE/stack.log" >&2; exit 1; }
uv run python scripts/demo_seed.py
echo "stop with: touch $STATE/stop"
