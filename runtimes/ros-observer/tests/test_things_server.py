"""The Things, the HTTP surface and the claim that there is no command surface."""

from __future__ import annotations

import http.client
import json
import re
import threading
from pathlib import Path
from typing import Any

import pytest
from pap_device_sdk import WotHttpAdapter
from pap_device_sdk.wot import parse_td
from pap_ros_observer.server import serve
from pap_ros_observer.things import Property, Thing, build_things

SRC = Path(__file__).resolve().parents[1] / "src" / "pap_ros_observer"


def readers() -> tuple[dict[str, Any], dict[str, Any]]:
    graph = {k: (lambda k=k: {"k": k}) for k in ("summary", "nodes", "topics", "expected", "clock")}
    robot = {k: (lambda k=k: {"k": k}) for k in ("joint_states", "transforms", "controllers", "diagnostics")}
    return graph, robot


@pytest.fixture
def server() -> Any:
    graph, robot = readers()
    things = build_things(graph, robot, lambda: {"observer": "test"})
    things["boom"] = Thing("boom", "Boom", "a failing reader", {"p": Property("p", {"type": "object"}, lambda: 1 / 0)})
    httpd = serve(things, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address
    httpd.shutdown()


def call(addr: tuple[str, int], method: str, path: str) -> tuple[int, Any]:
    c = http.client.HTTPConnection(addr[0], addr[1], timeout=5)
    c.request(method, path)
    r = c.getresponse()
    body = r.read()
    return r.status, (json.loads(body) if body else None)


def test_no_thing_description_declares_an_action() -> None:
    graph, robot = readers()
    for key, thing in build_things(graph, robot, lambda: {}).items():
        td = thing.td()
        assert "actions" not in td and "events" not in td, key
        for name, p in td["properties"].items():
            assert p["readOnly"] is True and p["writeOnly"] is False, (key, name)
            assert [f["op"] for f in p["forms"]] == [["readproperty"]], (key, name)


def test_the_platform_adapter_discovers_properties_only_and_no_simulated_claim(server: Any) -> None:
    url = f"http://{server[0]}:{server[1]}"
    devices = {d.key: d for d in WotHttpAdapter(url).discover()}
    assert {"ros-graph", "ros-robot"} <= set(devices)
    for key in ("ros-graph", "ros-robot"):
        d = devices[key]
        assert [a for a in d.affordances if a.kind == "action"] == []
        assert d.declares_simulated is False  # an observer never claims a device is simulated: the operator decides
    assert WotHttpAdapter(url).read_property("ros-graph", "summary") == {"k": "summary"}
    names = {a.name for a in devices["ros-robot"].affordances}
    assert names == {"joint_states", "transforms", "controllers", "diagnostics"}


def test_only_get_and_head_are_served(server: Any) -> None:
    assert call(server, "GET", "/ros-graph/summary") == (200, {"k": "summary"})
    assert call(server, "HEAD", "/ros-graph/summary")[0] == 200
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        status, body = call(server, method, "/ros-graph/summary")
        assert status == 405 and "read-only" in body["detail"], method
    assert call(server, "POST", "/ros-robot/anything")[0] == 405


def test_unknown_paths_are_404_and_a_failing_reader_answers_500(server: Any) -> None:
    assert call(server, "GET", "/nope")[0] == 404
    assert call(server, "GET", "/ros-graph/nope")[0] == 404
    assert call(server, "GET", "/ros-graph/summary/extra")[0] == 404
    status, body = call(server, "GET", "/boom/p")
    assert status == 500 and "ZeroDivisionError" in body["detail"]


def test_parse_td_of_a_thing_with_no_properties_still_has_no_actions() -> None:
    td = Thing("e", "Empty", "", {}).td()
    assert parse_td("e", td).affordances == []


# ---------------------------------------------------------------------------------------------- source scan


def code(name: str) -> str:
    """The module's code without comments and docstrings, so a word in prose cannot satisfy or break a rule."""
    import ast

    tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            node.value.value = ""
    return ast.unparse(tree)


def test_the_observer_has_no_means_to_command_a_robot() -> None:
    forbidden = [
        r"create_publisher", r"\.publish\(", r"create_service", r"ActionClient", r"ActionServer", r"send_goal",
        r"set_parameters", r"SetParameters", r"call\(", r"switch_controller", r"SwitchController", r"Twist",
        r"cmd_vel", r"JointTrajectory", r"FollowJointTrajectory", r"subprocess", r"os\.system", r"Popen",
    ]  # fmt: skip
    for name in ("node.py", "model.py", "things.py", "server.py", "__main__.py"):
        text = code(name)
        for pat in forbidden:
            assert not re.search(pat, text), f"{name} contains {pat!r}"


def test_the_only_client_is_the_list_controllers_query() -> None:
    node = code("node.py")
    assert len(re.findall(r"\.create_client\(", node)) == 1
    assert len(re.findall(r"\.call_async\(", node)) == 1
    assert "get_service(LIST_CONTROLLERS)" in node
    assert re.search(r"LIST_CONTROLLERS = 'controller_manager_msgs/srv/ListControllers'", node)
    # and the service it queries is chosen only by that exact type, never by a name a caller supplied
    assert "if LIST_CONTROLLERS not in types" in node


def test_a_non_finite_value_is_sent_as_null_so_any_strict_parser_accepts_the_response() -> None:
    things = {
        "t": Thing(
            "t",
            "T",
            "",
            {"p": Property("p", {"type": "object"}, lambda: {"effort": float("nan"), "x": [float("inf"), 1.0]})},
        )
    }
    httpd = serve(things, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
        c.request("GET", "/t/p")
        raw = c.getresponse().read().decode()
    finally:
        httpd.shutdown()

    def refuse(token: str) -> None:
        raise ValueError(f"not JSON: {token}")

    assert json.loads(raw, parse_constant=refuse) == {"effort": None, "x": [None, 1.0]}
