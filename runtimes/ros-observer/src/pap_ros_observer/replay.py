"""Serve a RECORDED snapshot through the same Things as the live observer, for tests and demos without ROS.

The snapshot comes from tests_ros/test_live_graph.py against a real graph (PAP_CAPTURE_SNAPSHOT). Replay changes
nothing in it except one field: `connectivity` says `recorded_not_live: true` and where the data came from, so no
consumer can mistake a replay for a live graph. Ages in a snapshot are the ages at capture time and do not advance.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .server import serve
from .things import build_things


def load(path: Path | str) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema") != "pap.ros-observer.snapshot/1":
        raise ValueError("not a pap.ros-observer.snapshot/1 file")
    return doc


def replay_server(path: Path | str, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    doc = load(path)
    things = doc["things"]

    def reader(thing: str, prop: str) -> Callable[[], Any]:
        return lambda: things[thing][prop]

    names = (("summary", "summary"), ("nodes", "nodes"), ("topics", "topics"), ("expected", "expected_topics"))
    graph = {k: reader("ros-graph", p) for k, p in (*names, ("clock", "clock"))}
    robot = {k: reader("ros-robot", k) for k in ("joint_states", "transforms", "controllers", "diagnostics")}
    conn = {**things["ros-graph"]["connectivity"], "recorded_not_live": True, "recorded_from": doc["source"]}
    return serve(build_things(graph, robot, lambda: conn), host, port)
