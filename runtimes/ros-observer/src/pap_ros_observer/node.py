"""The ROS 2 side: a node that only listens.

It creates subscriptions and, for controller states, a client for ONE service type (controller_manager_msgs
ListControllers, a query that changes nothing). It creates no publisher, no action client, no service server and no
timer that talks to a robot. tests/test_read_only.py scans this file for anything else.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from datetime import UTC, datetime
from typing import Any

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.utilities import get_rmw_implementation_identifier
from rosidl_runtime_py.utilities import get_message, get_service

from . import __version__
from .model import (
    HEAVY_TYPES,
    ClockTracker,
    DiagnosticsTracker,
    ExpectedTopic,
    JointTracker,
    TfTracker,
    TopicTracker,
    check_expected,
    is_hidden,
    summarize,
)

NODE_NAME = "pap_ros_observer"
LIST_CONTROLLERS = "controller_manager_msgs/srv/ListControllers"
MAX_TOPICS = int(os.environ.get("PAP_ROS_OBSERVER_MAX_TOPICS", "300"))


def _stamp(msg: Any) -> float | None:
    try:
        return float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9
    except AttributeError:
        return None


class Observer(Node):  # type: ignore[misc]
    def __init__(self, expected: list[ExpectedTopic], include_hidden: bool = False) -> None:
        super().__init__(NODE_NAME)
        self.include_hidden = include_hidden
        self.lock = threading.RLock()
        self.expected = expected
        self.started_mono = time.monotonic()
        self.started_wall = datetime.now(UTC).isoformat()
        self.topics: dict[str, TopicTracker] = {}
        self.subs: dict[str, Any] = {}
        self.nodes: list[dict[str, str]] = []
        self.sim_clock = ClockTracker()
        self.joints: dict[str, JointTracker] = {}
        self.tf = TfTracker()
        self.diag = DiagnosticsTracker()
        self.controllers: dict[str, dict[str, Any]] = {}  # manager service -> {queried, controllers | error}
        self.svc_clients: dict[str, Any] = {}
        self.graph_polls = 0
        self.last_poll_mono: float | None = None
        self.create_timer(1.0, self._poll_graph)
        self.create_timer(2.0, self._poll_controllers)
        self._poll_graph()

    # ------------------------------------------------------------------------------------------------ discovery
    def _qos_for(self, topic: str) -> tuple[QoSProfile, bool]:
        infos = self.get_publishers_info_by_topic(topic)
        latched = bool(infos) and all(i.qos_profile.durability == DurabilityPolicy.TRANSIENT_LOCAL for i in infos)
        reliable = bool(infos) and all(i.qos_profile.reliability == ReliabilityPolicy.RELIABLE for i in infos)
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE if (latched and reliable) else ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL if latched else DurabilityPolicy.VOLATILE,
        )
        return qos, latched

    def _poll_graph(self) -> None:
        now = time.monotonic()
        found = self.get_topic_names_and_types()
        names = self.get_node_names_and_namespaces()
        with self.lock:
            self.graph_polls += 1
            self.last_poll_mono = now
            self.nodes = [
                {"name": (ns.rstrip("/") + "/" + n), "namespace": ns}
                for n, ns in names
                if n != NODE_NAME and (self.include_hidden or not is_hidden(n))
            ]
            self.nodes.sort(key=lambda x: x["name"])
            for name, types in found:
                if is_hidden(name) and not self.include_hidden:
                    continue
                t = self.topics.get(name)
                if t is None:
                    t = self.topics[name] = TopicTracker(name, list(types), now)
                t.types = list(types)
                t.publishers = self.count_publishers(name)
                t.subscribers = max(0, self.count_subscribers(name) - (1 if name in self.subs else 0))
                if name == "/clock":
                    self.sim_clock.publishers = t.publishers
                if name not in self.subs and not t.not_sampled_reason:
                    self._subscribe(t)
            gone = set(self.topics) - {n for n, _ in found}
            for name in gone:  # the topic left the graph: keep its history, show no publishers
                self.topics[name].publishers = 0
                self.topics[name].subscribers = 0

    def _subscribe(self, t: TopicTracker) -> None:
        if len(self.subs) >= MAX_TOPICS:
            t.not_sampled_reason = f"observer topic cap ({MAX_TOPICS}) reached"
            return
        type_str = t.types[0] if t.types else ""
        if type_str in HEAVY_TYPES:
            t.not_sampled_reason = "heavy payload type: not subscribed"
            return
        if t.publishers == 0:
            return  # subscribe once someone publishes, with a QoS that fits them
        try:
            cls = get_message(type_str)
        except (ModuleNotFoundError, AttributeError, ValueError):
            t.not_sampled_reason = "message type not installed here"
            return
        qos, latched = self._qos_for(t.name)
        t.latched = latched
        cb = self._callback_for(t, type_str)
        raw = cb is None
        sub = self.create_subscription(cls, t.name, cb or self._raw_callback(t), qos, raw=raw)
        self.subs[t.name] = sub
        t.sampled = True

    def _callback_for(self, t: TopicTracker, type_str: str) -> Any:
        name = t.name
        if name == "/clock" and type_str == "rosgraph_msgs/msg/Clock":
            return lambda m: self._on_clock(t, m)
        if type_str == "sensor_msgs/msg/JointState":
            self.joints.setdefault(name, JointTracker())
            return lambda m: self._on_joints(t, m)
        if name in ("/tf", "/tf_static") and type_str == "tf2_msgs/msg/TFMessage":
            return lambda m: self._on_tf(t, m, static=(name == "/tf_static"))
        if name == "/diagnostics" and type_str == "diagnostic_msgs/msg/DiagnosticArray":
            return lambda m: self._on_diag(t, m)
        return None

    # ------------------------------------------------------------------------------------------------ callbacks
    def _raw_callback(self, t: TopicTracker) -> Any:
        def cb(_data: bytes) -> None:
            with self.lock:
                t.on_message(time.monotonic())

        return cb

    def _on_clock(self, t: TopicTracker, m: Any) -> None:
        now = time.monotonic()
        sim = float(m.clock.sec) + float(m.clock.nanosec) * 1e-9
        with self.lock:
            t.on_message(now, sim)
            self.sim_clock.on_clock(now, sim)

    def _on_joints(self, t: TopicTracker, m: Any) -> None:
        now = time.monotonic()
        with self.lock:
            t.on_message(now, _stamp(m))
            self.joints[t.name].on_message(
                now, _stamp(m), list(m.name), list(m.position), list(m.velocity), list(m.effort)
            )

    def _on_tf(self, t: TopicTracker, m: Any, static: bool) -> None:
        now = time.monotonic()
        with self.lock:
            t.on_message(now)
            for tr in m.transforms:
                v, q = tr.transform.translation, tr.transform.rotation
                self.tf.on_transform(
                    now, tr.header.frame_id, tr.child_frame_id, static, (v.x, v.y, v.z), (q.x, q.y, q.z, q.w)
                )

    def _on_diag(self, t: TopicTracker, m: Any) -> None:
        now = time.monotonic()
        with self.lock:
            t.on_message(now, _stamp(m))
            for s in m.status:
                level = s.level[0] if isinstance(s.level, bytes) else int(s.level)
                self.diag.on_status(now, s.name, level, s.message, s.hardware_id, {kv.key: kv.value for kv in s.values})

    # ------------------------------------------------------------------------------------------ controller query
    def _poll_controllers(self) -> None:
        """The one service this node calls: the controller manager's list_controllers (a query, nothing changes)."""
        try:
            cls = get_service(LIST_CONTROLLERS)
        except (ModuleNotFoundError, AttributeError, ValueError):
            return
        for svc, types in self.get_service_names_and_types():
            if LIST_CONTROLLERS not in types:
                continue
            client = self.svc_clients.get(svc)
            if client is None:
                client = self.svc_clients[svc] = self.create_client(cls, svc)
            if not client.service_is_ready():
                with self.lock:
                    self.controllers.setdefault(svc, {})["error"] = "service not ready"
                continue
            fut = client.call_async(cls.Request())
            fut.add_done_callback(lambda f, s=svc: self._on_controllers(s, f))

    def _on_controllers(self, svc: str, fut: Any) -> None:
        now = time.monotonic()
        with self.lock:
            try:
                res = fut.result()
                self.controllers[svc] = {
                    "queried": now,
                    "controllers": [
                        {
                            "name": c.name,
                            "type": c.type,
                            "state": c.state,
                            "claimed_interfaces": len(c.claimed_interfaces),
                            "is_chained": bool(getattr(c, "is_chained", False)),
                        }
                        for c in res.controller
                    ],
                }
            except Exception as e:  # noqa: BLE001  (any failure of the query is an observation, not a crash)
                self.controllers[svc] = {"error": f"{type(e).__name__}: {e}"}

    # ---------------------------------------------------------------------------------------------- properties
    def _topics(self, now: float) -> list[dict[str, Any]]:
        return [self.topics[n].as_dict(now) for n in sorted(self.topics)]

    def read_summary(self) -> dict[str, Any]:
        now = time.monotonic()
        with self.lock:
            return summarize(
                self._topics(now), check_expected(self.expected, self.topics, now), self.sim_clock.as_dict(now)
            ) | {"nodes": len(self.nodes)}

    def read_nodes(self) -> list[dict[str, str]]:
        with self.lock:
            return list(self.nodes)

    def read_topics(self) -> list[dict[str, Any]]:
        with self.lock:
            return self._topics(time.monotonic())

    def read_expected(self) -> list[dict[str, Any]]:
        with self.lock:
            return check_expected(self.expected, self.topics, time.monotonic())

    def read_clock(self) -> dict[str, Any]:
        with self.lock:
            return self.sim_clock.as_dict(time.monotonic())

    def read_joint_states(self) -> dict[str, Any]:
        now = time.monotonic()
        with self.lock:
            return {
                "sources": [{"topic": n, **j.as_dict(now, self.topics.get(n))} for n, j in sorted(self.joints.items())]
            }

    def read_transforms(self) -> dict[str, Any]:
        with self.lock:
            return self.tf.as_dict(time.monotonic())

    def read_controllers(self) -> dict[str, Any]:
        now = time.monotonic()
        with self.lock:
            managers = []
            for svc, v in sorted(self.controllers.items()):
                q = v.get("queried")
                managers.append(
                    {
                        "service": svc,
                        "controllers": v.get("controllers", []),
                        "error": v.get("error"),
                        "age_s": None if q is None else round(max(0.0, now - q), 3),
                    }
                )
            return {"available": bool(managers), "managers": managers}

    def read_diagnostics(self) -> dict[str, Any]:
        with self.lock:
            return self.diag.as_dict(time.monotonic())

    def read_observer(self) -> dict[str, Any]:
        now = time.monotonic()
        with self.lock:
            return {
                "observer": "pap-ros-observer",
                "version": __version__,
                "command_surface": "none",
                "read_only_queries": [LIST_CONTROLLERS],
                "host": socket.gethostname(),
                "pid": os.getpid(),
                "ros_distro": os.environ.get("ROS_DISTRO"),
                "rmw": get_rmw_implementation_identifier(),
                "domain_id": int(os.environ.get("ROS_DOMAIN_ID", "0")),
                "started_wall_utc": self.started_wall,
                "uptime_s": round(now - self.started_mono, 3),
                "graph_polls": self.graph_polls,
                "last_graph_poll_age_s": None if self.last_poll_mono is None else round(now - self.last_poll_mono, 3),
                "nodes_seen": len(self.nodes),
                "topics_seen": len(self.topics),
                "subscriptions": len(self.subs),
            }


def run(expected: list[ExpectedTopic], host: str, port: int, include_hidden: bool = False) -> None:
    from .server import serve
    from .things import build_things

    rclpy.init()
    obs = Observer(expected, include_hidden)
    things = build_things(
        graph={
            "summary": obs.read_summary,
            "nodes": obs.read_nodes,
            "topics": obs.read_topics,
            "expected": obs.read_expected,
            "clock": obs.read_clock,
        },
        robot={
            "joint_states": obs.read_joint_states,
            "transforms": obs.read_transforms,
            "controllers": obs.read_controllers,
            "diagnostics": obs.read_diagnostics,
        },
        observer=obs.read_observer,
    )
    httpd = serve(things, host, port)
    threading.Thread(target=httpd.serve_forever, name="http", daemon=True).start()
    try:
        rclpy.spin(obs)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass  # asked to stop
    finally:
        httpd.shutdown()
        obs.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
