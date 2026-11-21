"""What the observer knows and how it judges it. Pure Python: no ROS imports, so the judgements are testable anywhere.

Every age is measured on a monotonic clock supplied by the caller (never the host wall clock, which on WSL steps back
about a second every half minute). A message's own header stamp is kept as a separate fact: a stamp can claim freshness
the data does not have (a joint-state merger keeps stamping frozen positions), so freshness here is "when did we last
receive something", and joints additionally report how long their value has been unchanged.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# A topic is never judged stale in under STALE_MIN_S, nor before STALE_PERIODS of its own measured periods passed.
STALE_MIN_S = 2.0
STALE_PERIODS = 5.0
# Right after the observer subscribed, silence means nothing yet.
GRACE_S = 3.0
WINDOW = 64  # receive times kept per topic for the rate

# Types whose payload is too large to subscribe to just to learn whether data arrives.
HEAVY_TYPES = frozenset(
    {
        "sensor_msgs/msg/Image",
        "sensor_msgs/msg/CompressedImage",
        "sensor_msgs/msg/PointCloud2",
        "sensor_msgs/msg/PointCloud",
        "nav_msgs/msg/OccupancyGrid",
        "grid_map_msgs/msg/GridMap",
        "visualization_msgs/msg/MarkerArray",
    }
)

DIAG_LEVEL = {0: "OK", 1: "WARN", 2: "ERROR", 3: "STALE"}


def finite(x: float | None) -> float | None:
    """NaN and infinities are not JSON; a sensor that reports one is reporting no value, sent as null."""
    return x if x is not None and math.isfinite(x) else None


def is_hidden(name: str) -> bool:
    """ROS convention (`ros2 node list`, `ros2 topic list`): a name with any segment starting with `_` is hidden."""
    return any(seg.startswith("_") for seg in name.split("/") if seg)


@dataclass
class TopicTracker:
    name: str
    types: list[str]
    created: float  # monotonic time the observer first saw the topic
    publishers: int = 0
    subscribers: int = 0
    sampled: bool = False
    # Every publisher is transient-local. That alone does not mean "publishes once" (ros2_control streams /joint_states
    # with this QoS): only a topic that has delivered at most one message is reported as latched.
    latched: bool = False
    not_sampled_reason: str | None = None
    count: int = 0
    first_rx: float | None = None
    last_rx: float | None = None
    last_stamp_s: float | None = None
    rx: deque[float] = field(default_factory=lambda: deque(maxlen=WINDOW))

    def on_message(self, now: float, stamp_s: float | None = None) -> None:
        self.count += 1
        self.first_rx = self.first_rx if self.first_rx is not None else now
        self.last_rx = now
        self.rx.append(now)
        if stamp_s is not None:
            self.last_stamp_s = stamp_s

    def median_period_s(self) -> float | None:
        if len(self.rx) < 3:
            return None
        gaps = [b - a for a, b in zip(self.rx, list(self.rx)[1:], strict=False) if b > a]
        return statistics.median(gaps) if gaps else None

    def rate_hz(self) -> float | None:
        p = self.median_period_s()
        return round(1.0 / p, 3) if p else None

    def age_s(self, now: float) -> float | None:
        return None if self.last_rx is None else max(0.0, now - self.last_rx)

    def stale_after_s(self) -> float:
        p = self.median_period_s()
        return max(STALE_MIN_S, STALE_PERIODS * p) if p else STALE_MIN_S

    def state(self, now: float) -> str:
        """not_sampled | no_publishers | pending | never | latched | fresh | stale."""
        if not self.sampled:
            if self.not_sampled_reason:
                return "not_sampled"
            return "no_publishers" if self.publishers == 0 else "pending"
        if self.count == 0:
            if self.publishers == 0:
                return "no_publishers"
            return "pending" if now - self.created < GRACE_S else "never"
        if self.latched and self.count <= 1:
            return "latched"  # transient-local with a single message: published once, so its age says nothing
        age = self.age_s(now)
        assert age is not None
        return "stale" if age > self.stale_after_s() else "fresh"

    def as_dict(self, now: float) -> dict[str, Any]:
        age = self.age_s(now)
        return {
            "name": self.name,
            "types": self.types,
            "publishers": self.publishers,
            "subscribers": self.subscribers,
            "state": self.state(now),
            "latched": self.latched,
            "not_sampled_reason": self.not_sampled_reason,
            "messages": self.count,
            "rate_hz": self.rate_hz(),
            "age_s": None if age is None else round(age, 3),
            "stale_after_s": round(self.stale_after_s(), 3),
            "header_stamp_s": self.last_stamp_s,
        }


@dataclass
class ExpectedTopic:
    name: str
    required: bool = True
    max_age_s: float | None = None
    note: str = ""

    @staticmethod
    def parse(items: list[dict[str, Any]]) -> list[ExpectedTopic]:
        return [
            ExpectedTopic(str(i["name"]), bool(i.get("required", True)), i.get("max_age_s"), str(i.get("note", "")))
            for i in items
        ]


def check_expected(
    expected: list[ExpectedTopic], trackers: dict[str, TopicTracker], now: float
) -> list[dict[str, Any]]:
    """present/missing/stale for each topic the profile says should exist. Silence is reported, never filled in."""
    out = []
    for e in expected:
        t = trackers.get(e.name)
        if t is None:
            state, age = "missing", None
        else:
            state, age = t.state(now), t.age_s(now)
            if e.max_age_s is not None and age is not None and age > e.max_age_s:
                state = "stale"
        out.append(
            {
                "name": e.name,
                "required": e.required,
                "state": state,
                "age_s": None if age is None else round(age, 3),
                "max_age_s": e.max_age_s,
                "note": e.note,
            }
        )
    return out


@dataclass
class ClockTracker:
    """/clock: is there a simulation clock, does it advance, and does it ever go backwards."""

    publishers: int = 0
    count: int = 0
    first_sim: float | None = None
    first_rx: float | None = None
    last_sim: float | None = None
    last_rx: float | None = None
    backward_jumps: int = 0
    largest_backward_s: float = 0.0

    def on_clock(self, now: float, sim_s: float) -> None:
        if self.last_sim is not None and sim_s < self.last_sim:
            self.backward_jumps += 1
            self.largest_backward_s = max(self.largest_backward_s, self.last_sim - sim_s)
        if self.first_sim is None:
            self.first_sim, self.first_rx = sim_s, now
        self.count += 1
        self.last_sim, self.last_rx = sim_s, now

    def as_dict(self, now: float) -> dict[str, Any]:
        if self.count == 0:
            state = "absent" if self.publishers == 0 else "silent"
        else:
            assert self.last_rx is not None
            state = "stale" if now - self.last_rx > STALE_MIN_S else "running"
        rtf = None
        if self.count > 1 and self.first_rx is not None and self.last_rx is not None and self.last_rx > self.first_rx:
            assert self.first_sim is not None and self.last_sim is not None
            rtf = round((self.last_sim - self.first_sim) / (self.last_rx - self.first_rx), 4)
        return {
            "state": state,
            "publishers": self.publishers,
            "sim_time_s": self.last_sim,
            "age_s": None if self.last_rx is None else round(max(0.0, now - self.last_rx), 3),
            "real_time_factor": rtf,
            "monotonic": self.backward_jumps == 0,
            "backward_jumps": self.backward_jumps,
            "largest_backward_s": round(self.largest_backward_s, 6),
            "messages": self.count,
        }


@dataclass
class JointTracker:
    """Latest joint states, and per joint how long its position has not changed.

    A frozen value can keep a fresh header stamp, so the time since the last change is reported separately.
    """

    count: int = 0
    last_rx: float | None = None
    stamp_s: float | None = None
    names: list[str] = field(default_factory=list)
    position: dict[str, float | None] = field(default_factory=dict)
    velocity: dict[str, float | None] = field(default_factory=dict)
    effort: dict[str, float | None] = field(default_factory=dict)
    changed_at: dict[str, float] = field(default_factory=dict)
    epsilon: float = 1e-9

    def on_message(
        self, now: float, stamp_s: float | None, names: list[str], pos: list[float], vel: list[float], eff: list[float]
    ) -> None:
        self.count += 1
        self.last_rx, self.stamp_s = now, stamp_s
        self.names = list(names)
        for i, n in enumerate(names):
            if i < len(pos):
                p = finite(pos[i])
                old = self.position.get(n)
                if (
                    n not in self.position
                    or (p is None) != (old is None)
                    or (p is not None and old is not None and abs(p - old) > self.epsilon)
                ):
                    self.changed_at[n] = now
                self.position[n] = p
            if i < len(vel):
                self.velocity[n] = finite(vel[i])
            if i < len(eff):
                self.effort[n] = finite(eff[i])

    def as_dict(self, now: float, topic: TopicTracker | None) -> dict[str, Any]:
        state = topic.state(now) if topic else "missing"
        joints = [
            {
                "name": n,
                "position": self.position.get(n),
                "velocity": self.velocity.get(n),
                "effort": self.effort.get(n),
                "unchanged_for_s": None if n not in self.changed_at else round(max(0.0, now - self.changed_at[n]), 3),
            }
            for n in self.names
        ]
        return {
            "state": state,
            "age_s": None if self.last_rx is None else round(max(0.0, now - self.last_rx), 3),
            "header_stamp_s": self.stamp_s,
            "messages": self.count,
            "joints": joints,
        }


@dataclass
class TfTracker:
    frames: dict[str, dict[str, Any]] = field(default_factory=dict)  # child -> latest observation

    def on_transform(
        self, now: float, parent: str, child: str, static: bool, tr: tuple[float, float, float], rot: tuple[float, ...]
    ) -> None:
        prev = self.frames.get(child)
        self.frames[child] = {
            "parent": parent,
            "static": static,
            "translation": list(tr),
            "rotation": list(rot),
            "last_rx": now,
            "updates": (prev["updates"] + 1) if prev else 1,
        }

    def as_dict(self, now: float) -> dict[str, Any]:
        frames = []
        for child, f in sorted(self.frames.items()):
            frames.append(
                {
                    "child": child,
                    "parent": f["parent"],
                    "static": f["static"],
                    "translation": f["translation"],
                    "rotation": f["rotation"],
                    "updates": f["updates"],
                    # A static transform is published once: its age says nothing about health.
                    "age_s": None if f["static"] else round(max(0.0, now - f["last_rx"]), 3),
                }
            )
        parents = {f["parent"] for f in frames}
        children = {f["child"] for f in frames}
        return {"frames": frames, "roots": sorted(parents - children), "count": len(frames)}


@dataclass
class DiagnosticsTracker:
    statuses: dict[str, dict[str, Any]] = field(default_factory=dict)
    count: int = 0

    def on_status(
        self, now: float, name: str, level: int, message: str, hardware_id: str, values: dict[str, str]
    ) -> None:
        self.count += 1
        self.statuses[name] = {
            "name": name,
            "level": DIAG_LEVEL.get(level, str(level)),
            "message": message,
            "hardware_id": hardware_id,
            "values": dict(list(values.items())[:12]),
            "last_rx": now,
        }

    def as_dict(self, now: float) -> dict[str, Any]:
        items = [{**{k: v for k, v in s.items() if k != "last_rx"}, "age_s": round(max(0.0, now - s["last_rx"]), 3)}
                 for s in sorted(self.statuses.values(), key=lambda s: s["name"])]  # fmt: skip
        return {"statuses": items, "messages": self.count, "state": "no_messages" if self.count == 0 else "received"}


def summarize(topics: list[dict[str, Any]], expected: list[dict[str, Any]], clock: dict[str, Any]) -> dict[str, Any]:
    """Counts only; every number is a count of observations above."""
    by_state: dict[str, int] = {}
    for t in topics:
        by_state[t["state"]] = by_state.get(t["state"], 0) + 1
    exp: dict[str, int] = {}
    for e in expected:
        exp[e["state"]] = exp.get(e["state"], 0) + 1
    problems = [
        e["name"] for e in expected if e["required"] and e["state"] in ("missing", "stale", "never", "no_publishers")
    ]
    return {
        "topics": len(topics),
        "topics_by_state": dict(sorted(by_state.items())),
        "expected_by_state": dict(sorted(exp.items())),
        "required_expected_problems": problems,
        "clock_state": clock["state"],
    }
