#!/usr/bin/env bash
# Start or stop a real ROS 2 graph (the OpenAMRobot upperbody MOCK bringup: real ros2_control controllers on mock
# hardware) and the read-only observer, inside the WSL distro that has ROS 2 Jazzy. For local live runs; CI has no ROS.
#
#   bash scripts/ros_stack.sh start     # prints the observer URL when it answers
#   bash scripts/ros_stack.sh status
#   bash scripts/ros_stack.sh stop
#
# Env: PAP_ROS_DISTRO_NAME (WSL distro, default openmhs-ros), PAP_ROS_DOMAIN (default 88), PAP_ROS_OBSERVER_PORT (8200),
#      PAP_ROS_OVERLAY (workspace install/setup.bash inside WSL, default ~/openamr_main/install/setup.bash).
# The observer only listens; the mock bringup is a throwaway simulation. Nothing here touches a real robot.
# The observer listens on all of WSL's interfaces so Windows can reach it through WSL's localhost forwarding; restrict
# that with a firewall rule if the machine is on an untrusted network.
set -euo pipefail
cd "$(dirname "$0")/.."
DISTRO="${PAP_ROS_DISTRO_NAME:-openmhs-ros}"
PORT="${PAP_ROS_OBSERVER_PORT:-8200}"
W="$(pwd -W 2>/dev/null || pwd)"
REPO_WSL="/mnt/$(printf %s "${W:0:1}" | tr A-Z a-z)${W:2}"
export MSYS_NO_PATHCONV=1
export PAP_ROS_DOMAIN="${PAP_ROS_DOMAIN:-88}" PAP_ROS_OBSERVER_PORT="$PORT"
export WSLENV="PAP_ROS_DOMAIN:PAP_ROS_OBSERVER_PORT:PAP_ROS_OVERLAY${WSLENV:+:$WSLENV}"
# Output goes to a file, not a pipe: wsl.exe would otherwise wait for the background processes to close the pipe.
inside() {
  local out; out="$(mktemp)"
  timeout 60 wsl.exe -d "$DISTRO" -- bash "$REPO_WSL/scripts/ros_stack_wsl.sh" "$1" </dev/null >"$out" 2>&1 || true
  tr -d '\0' <"$out"; rm -f "$out"
}

case "${1:-}" in
  start)
    # One wsl.exe session stays open for the life of the stack (WSL ends background processes when their session ends).
    mkdir -p var
    nohup wsl.exe -d "$DISTRO" -- bash "$REPO_WSL/scripts/ros_stack_wsl.sh" run </dev/null >var/ros-stack.log 2>&1 &
    echo $! >var/ros-stack.pid
    for _ in $(seq 1 90); do
      if curl -sf "http://127.0.0.1:$PORT/thing_descriptions/" >/dev/null 2>&1; then echo "observer: http://127.0.0.1:$PORT"; exit 0; fi
      sleep 1
    done
    echo "the observer did not answer within 90 s; see var/ros-stack.log and /tmp/pap-ros-observer.log inside WSL" >&2; exit 1 ;;
  stop)
    inside stop
    if [ -f var/ros-stack.pid ]; then kill "$(cat var/ros-stack.pid)" 2>/dev/null || true; rm -f var/ros-stack.pid; fi ;;
  status) inside status ;;
  *) echo "usage: bash scripts/ros_stack.sh start|stop|status" >&2; exit 2 ;;
esac
