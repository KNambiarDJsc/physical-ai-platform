"""ROS-001 against a real graph. The ground truth is `ros2` CLI output, taken independently of the observer."""

from __future__ import annotations

import os
import re
import signal
import time
from typing import Any

from conftest import Obs, eventually, run

DOMAIN_ID = int(os.environ.get("ROS_DOMAIN_ID", "88"))
CONTROLLERS = {
    "joint_state_broadcaster", "left_arm_controller", "right_arm_controller",
    "left_gripper_controller", "right_gripper_controller", "lift_controller",
}  # fmt: skip


def by_name(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {i["name"]: i for i in items}


def test_nodes_match_ros2_node_list(stack: dict[str, Any]) -> None:
    truth = {
        n
        for n in run("ros2 node list --no-daemon --spin-time 4", timeout=60).split()
        if n.startswith("/") and n != "/pap_ros_observer"
    }
    seen = {n["name"] for n in stack["obs"].prop("ros-graph", "nodes")}
    assert {"/controller_manager", "/robot_state_publisher"} <= truth
    assert seen == truth, f"observer {sorted(seen)} vs ros2 node list {sorted(truth)}"


def test_topics_match_ros2_topic_list_with_types_and_publisher_counts(stack: dict[str, Any]) -> None:
    truth = {}
    for line in run("ros2 topic list -t --no-daemon --spin-time 4", timeout=60).splitlines():
        m = re.match(r"^(/\S+) \[(\S+)\]$", line.strip())
        if m:
            truth[m.group(1)] = m.group(2)
    topics = by_name(stack["obs"].prop("ros-graph", "topics"))
    for name, typ in truth.items():
        assert name in topics and topics[name]["types"][0] == typ, name
    js = topics["/joint_states"]
    assert js["publishers"] == len(
        re.findall(
            r"Node name:",
            run("ros2 topic info /joint_states -v --spin-time 4", timeout=60).split("Subscription count")[0],
        )
    )
    assert js["state"] == "fresh" and js["rate_hz"] and js["rate_hz"] > 5, js


def test_joint_states_match_a_cli_echo(stack: dict[str, Any]) -> None:
    echo = run("ros2 topic echo --once --field name /joint_states", timeout=20)
    truth = re.findall(r"'([^']+)'", echo)  # the CLI prints a Python list: ['lift_joint', 'openarm_left_joint1', ...]
    src = stack["obs"].prop("ros-robot", "joint_states")["sources"]
    js = next(s for s in src if s["topic"] == "/joint_states")
    assert truth and [j["name"] for j in js["joints"]] == truth
    assert js["state"] == "fresh" and js["age_s"] < 1.0
    assert all(isinstance(j["position"], float) for j in js["joints"])


def test_controllers_match_the_controller_manager(stack: dict[str, Any]) -> None:
    out = run("ros2 service call /controller_manager/list_controllers controller_manager_msgs/srv/ListControllers",
              timeout=30)  # fmt: skip
    truth = dict(re.findall(r"name='([^']+)',\s*state='([^']+)'", out))
    assert set(truth) == CONTROLLERS and set(truth.values()) == {"active"}
    mgr = stack["obs"].prop("ros-robot", "controllers")["managers"][0]
    assert mgr["service"] == "/controller_manager/list_controllers" and mgr["error"] is None
    assert {c["name"]: c["state"] for c in mgr["controllers"]} == truth
    assert mgr["age_s"] < 5


def test_transforms_cover_the_robot_description(stack: dict[str, Any]) -> None:
    echo = run("ros2 topic echo --once --field transforms /tf_static", timeout=20)
    truth = set(re.findall(r"child_frame_id='([^']+)'", echo))
    tf = stack["obs"].prop("ros-robot", "transforms")
    frames = {f["child"] for f in tf["frames"]}
    assert truth and truth <= frames, sorted(truth - frames)
    static = {f["child"] for f in tf["frames"] if f["static"]}
    assert truth <= static and all(f["age_s"] is None for f in tf["frames"] if f["static"])
    assert tf["roots"], "a frame tree has a root"


def test_expected_topics_report_what_the_graph_does_and_does_not_publish(stack: dict[str, Any]) -> None:
    exp = by_name(stack["obs"].prop("ros-graph", "expected_topics"))
    assert exp["/clock"]["state"] == "missing" and exp["/clock"]["required"] is False  # no simulator in this bringup
    assert exp["/joint_states"]["state"] == "fresh"
    assert exp["/tf_static"]["state"] == "latched"
    assert exp["/robot_description"]["state"] == "latched"
    clock = stack["obs"].prop("ros-graph", "clock")
    assert clock["state"] == "absent" and clock["sim_time_s"] is None and clock["real_time_factor"] is None
    assert stack["obs"].prop("ros-graph", "summary")["required_expected_problems"] == []


def test_diagnostics_match_what_the_controller_manager_publishes(stack: dict[str, Any]) -> None:
    """Jazzy's ros2_control_node publishes /diagnostics; the observer must show exactly those statuses, not invent any."""
    echo = run("ros2 topic echo --once --field status /diagnostics", timeout=30)
    truth = set(re.findall(r"name='([^']+)'", echo))
    assert truth, f"the CLI saw no diagnostics: {echo[:200]!r}"
    diag = eventually(
        lambda: (d := stack["obs"].prop("ros-robot", "diagnostics"))["statuses"] and d, 20, "diagnostics received"
    )
    seen = {s["name"] for s in diag["statuses"]}
    assert truth <= seen, sorted(truth - seen)
    assert {s["level"] for s in diag["statuses"]} <= {"OK", "WARN", "ERROR", "STALE"}
    assert diag["state"] == "received" and all(s["age_s"] is not None for s in diag["statuses"])
    assert by_name(stack["obs"].prop("ros-graph", "topics"))["/diagnostics"]["state"] == "fresh"


def test_the_observers_own_footprint_on_the_graph_is_listening_only(stack: dict[str, Any]) -> None:
    info = run("ros2 node info /pap_ros_observer", timeout=30)

    def section(title: str) -> set[str]:
        m = re.search(rf"^\s*{title}:\n((?:\s{{4}}.*\n)*)", info, re.M)
        return {ln.split(":")[0].strip() for ln in (m.group(1).splitlines() if m else []) if ln.strip()}

    assert section("Publishers") <= {"/parameter_events", "/rosout"}, section("Publishers")  # rclpy's own defaults
    assert section("Action Clients") == set() and section("Action Servers") == set()
    assert section("Service Clients") == {"/controller_manager/list_controllers"}, section("Service Clients")
    assert len(section("Subscribers")) > 5


def test_real_staleness_when_the_publisher_really_stops(stack: dict[str, Any]) -> None:
    """Freeze the mock bringup's ros2_control_node (SIGSTOP): its /joint_states publisher goes silent for real."""
    o: Obs = stack["obs"]
    pid = int(run("pgrep -f ros2_control_node | head -1").split()[0])
    try:
        os.kill(pid, signal.SIGSTOP)
        t0 = time.monotonic()
        eventually(
            lambda: by_name(o.prop("ros-graph", "topics"))["/joint_states"]["state"] == "stale",
            20,
            "/joint_states stale",
        )
        waited = time.monotonic() - t0
        assert 1.0 < waited < 12, waited  # the documented threshold is max(2 s, 5 periods): stale only after about 2 s
        js = next(s for s in o.prop("ros-robot", "joint_states")["sources"] if s["topic"] == "/joint_states")
        assert js["state"] == "stale" and js["age_s"] > 2.0
        exp = by_name(o.prop("ros-graph", "expected_topics"))
        assert exp["/joint_states"]["state"] == "stale"
        assert "/joint_states" in o.prop("ros-graph", "summary")["required_expected_problems"]
    finally:
        os.kill(pid, signal.SIGCONT)
    eventually(
        lambda: by_name(o.prop("ros-graph", "topics"))["/joint_states"]["state"] == "fresh",
        20,
        "/joint_states fresh again",
    )
    assert o.prop("ros-graph", "summary")["required_expected_problems"] == []


def test_connectivity_describes_the_observer_process(stack: dict[str, Any]) -> None:
    c = stack["obs"].prop("ros-graph", "connectivity")
    assert (
        c["command_surface"] == "none"
        and c["ros_distro"] == "jazzy"
        and c["domain_id"] == int(os.environ.get("ROS_DOMAIN_ID", "88"))
    )
    assert c["rmw"].startswith("rmw_") and c["graph_polls"] >= 3 and c["last_graph_poll_age_s"] < 3
    assert c["subscriptions"] >= 5 and c["nodes_seen"] >= 2


def test_zz_capture_snapshot_for_platform_tests(stack: dict[str, Any]) -> None:
    """Only with PAP_CAPTURE_SNAPSHOT=<path>: save what this real graph reported, for tests that run without ROS.
    The file says where it came from; nothing in it is edited or invented."""
    import json
    import subprocess

    import pytest

    out = os.environ.get("PAP_CAPTURE_SNAPSHOT")
    if not out:
        pytest.skip("set PAP_CAPTURE_SNAPSHOT=<file> to capture")
    o: Obs = stack["obs"]
    time.sleep(3)  # let rates settle
    td = o.get("/thing_descriptions/")
    things = {t: {p: o.prop(t, p) for p in td[t]["properties"]} for t in td}
    ws = os.path.expanduser("~/openamr_main/src/openamr-upperbody-sw")
    sha = subprocess.run(
        ["git", "-C", ws, "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    doc = {
        "schema": "pap.ros-observer.snapshot/1",
        "recorded_not_live": True,
        "source": {
            "graph": "openamr-upperbody-sw ros2/openamrobot_upperbody_bringup mock.launch.py (mock_components, real controllers)",
            "software_commit": sha, "ros_distro": os.environ.get("ROS_DISTRO"), "domain_id": DOMAIN_ID,
            "captured_wall_utc": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        },
        "things": things,
    }  # fmt: skip
    from pathlib import Path

    Path(out).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
