#!/usr/bin/env bash
# Runs INSIDE the WSL distro (called by scripts/ros_stack.sh). The OpenAMRobot upperbody MOCK bringup (real ros2_control
# controllers on mock hardware) and the read-only observer. Nothing here touches a real robot.
#   ros_stack_wsl.sh run      foreground: start both, stay until stopped (WSL ends its processes when this exits)
#   ros_stack_wsl.sh stop     kill both
#   ros_stack_wsl.sh status
set +u
source /opt/ros/jazzy/setup.bash
source "${PAP_ROS_OVERLAY:-$HOME/openamr_main/install/setup.bash}"
set -u
export ROS_DOMAIN_ID="${PAP_ROS_DOMAIN:-88}" PYTHONDONTWRITEBYTECODE=1
HERE="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$HERE/runtimes/ros-observer/src:${PYTHONPATH:-}"
PORT="${PAP_ROS_OBSERVER_PORT:-8200}"

stop_all() {
  for p in '[p]ap_ros_observer' '[r]os2_control_node' '[r]obot_state_publisher' '[r]os2 launch' '[s]pawner'; do pkill -9 -f "$p" 2>/dev/null; done
}

case "${1:-}" in
  run)
    if pgrep -f '[r]os2_control_node' >/dev/null; then echo "a ROS stack is already running"; exit 1; fi
    trap 'stop_all' EXIT INT TERM
    ros2 launch openamrobot_upperbody_bringup mock.launch.py >/tmp/pap-ros-graph.log 2>&1 </dev/null &
    python3 -m pap_ros_observer serve --host 0.0.0.0 --port "$PORT" --profile openamr-upperbody.json >/tmp/pap-ros-observer.log 2>&1 </dev/null &
    echo "running (graph and observer); this session must stay open"
    wait ;;
  stop) stop_all; echo stopped ;;
  status) pgrep -af '[r]os2_control_node|[p]ap_ros_observer' | cut -c1-100 || echo "not running" ;;
  *) echo "usage: ros_stack_wsl.sh run|stop|status" >&2; exit 2 ;;
esac
