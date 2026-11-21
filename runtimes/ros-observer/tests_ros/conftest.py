"""Tests against a REAL ROS 2 graph. Run inside WSL (or any host with ROS 2 Jazzy and the OpenAMRobot upperbody overlay):

    ROS_DOMAIN_ID=88 python3 -m pytest runtimes/ros-observer/tests_ros -q

Skipped when ROS is absent, unless PAP_REQUIRE_ROS=1 (then a missing ROS is a failure, never a silent skip).
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "runtimes" / "ros-observer" / "src"
OVERLAY = os.environ.get("PAP_ROS_OVERLAY", str(Path.home() / "openamr_main" / "install" / "setup.bash"))
DOMAIN = os.environ.get("ROS_DOMAIN_ID", "88")


def have_ros() -> bool:
    try:
        import rclpy  # noqa: F401
    except ImportError:
        return False
    return Path(OVERLAY).is_file()


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    if have_ros():
        return
    if os.environ.get("PAP_REQUIRE_ROS") == "1":
        pytest.fail("PAP_REQUIRE_ROS=1 but ROS 2 or the OpenAMRobot overlay is unavailable")
    for it in items:
        it.add_marker(pytest.mark.skip(reason="ROS 2 Jazzy / overlay not available on this host"))


def sh(cmd: str, **kw: Any) -> subprocess.Popen[str]:
    """A bash command with ROS sourced, in its own process group so the whole tree can be killed."""
    env = {**os.environ, "ROS_DOMAIN_ID": DOMAIN, "PYTHONPATH": f"{SRC}:{os.environ.get('PYTHONPATH', '')}"}
    full = f"set +u; source /opt/ros/jazzy/setup.bash; source '{OVERLAY}'; set -u; {cmd}"
    return subprocess.Popen(["bash", "-c", full], env=env, text=True, start_new_session=True, **kw)


def run(cmd: str, timeout: float = 30) -> str:
    p = sh(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = p.communicate(timeout=timeout)
    return out


def kill_tree(p: subprocess.Popen[str]) -> None:
    for sig in (signal.SIGINT, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(p.pid), sig)
        except ProcessLookupError:
            return
        try:
            p.wait(timeout=8)
            return
        except subprocess.TimeoutExpired:
            continue


def eventually(cond: Callable[[], Any], timeout: float, what: str, every: float = 0.5) -> Any:
    end = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < end:
        try:
            last = cond()
            if last:
                return last
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(every)
    raise AssertionError(f"timed out after {timeout:g} s waiting for: {what} (last: {last!r})")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Obs:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"

    def get(self, path: str) -> Any:
        with urllib.request.urlopen(f"{self.base}{path}", timeout=5) as r:  # noqa: S310  (loopback test server)
            return json.loads(r.read())

    def prop(self, thing: str, name: str) -> Any:
        return self.get(f"/{thing}/{name}")


@pytest.fixture(scope="session")
def stack() -> Iterator[dict[str, Any]]:
    """The OpenAMRobot upperbody MOCK bringup (real ros2_control controllers on mock hardware) and the observer."""
    if run(
        "ros2 node list --no-daemon --spin-time 3 2>/dev/null | grep -c controller_manager || true", timeout=60
    ).strip() not in ("0", ""):
        pytest.fail(f"another ROS stack already runs on ROS_DOMAIN_ID={DOMAIN}; a second stack corrupts the run")
    graph = sh(
        "ros2 launch openamrobot_upperbody_bringup mock.launch.py", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    port = free_port()
    obs = sh(f"python3 -m pap_ros_observer serve --port {port} --profile openamr-upperbody.json",
             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)  # fmt: skip
    o = Obs(port)
    try:
        eventually(lambda: o.get("/thing_descriptions/"), 60, "the observer to answer")
        eventually(
            lambda: [c for m in o.prop("ros-robot", "controllers")["managers"] for c in m["controllers"]
                     if c["state"] == "active"].__len__() >= 6,
            120, "six controllers active in the mock bringup",
        )  # fmt: skip
        eventually(lambda: any(t["name"] == "/joint_states" and t["state"] == "fresh" for t in o.prop("ros-graph", "topics")),
                   30, "/joint_states fresh")  # fmt: skip
        yield {"obs": o, "graph": graph, "port": port}
    finally:
        kill_tree(obs)
        kill_tree(graph)
        subprocess.run(["bash", "-c", "pkill -9 -f ros2_control_node; pkill -9 -f robot_state_publisher"], check=False)
        time.sleep(1)


def have_python() -> str:
    return sys.executable
