"""Things: the observer's description of what it can show, as W3C Web of Things Thing Descriptions.

A Thing here is a title, a description and READ-ONLY properties. There is deliberately no way to declare an action: the
structure has no field for one, so the platform's adapter can only ever discover readable properties.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

WOT_CONTEXT = "https://www.w3.org/2022/wot/td/v1.1"


@dataclass(frozen=True)
class Property:
    description: str
    schema: dict[str, Any]
    read: Callable[[], Any]


@dataclass(frozen=True)
class Thing:
    key: str
    title: str
    description: str
    properties: dict[str, Property]

    def td(self) -> dict[str, Any]:
        props: dict[str, Any] = {}
        for name, p in self.properties.items():
            props[name] = {
                "title": p.description,
                "description": p.description,
                "readOnly": True,
                "writeOnly": False,
                **p.schema,
                "forms": [{"href": f"/{self.key}/{name}", "op": ["readproperty"]}],
            }
        return {
            "@context": WOT_CONTEXT,
            "title": self.title,
            "description": self.description,
            "securityDefinitions": {"no_security": {"scheme": "nosec", "description": "Loopback only; no security"}},
            "security": "no_security",
            "properties": props,
        }


def build_things(
    graph: dict[str, Callable[[], Any]], robot: dict[str, Callable[[], Any]], observer: Callable[[], Any]
) -> dict[str, Thing]:
    """The two Things. `graph` and `robot` map property names to readers (see node.py); `observer` describes us."""
    obj = {"type": "object"}
    arr = {"type": "array"}
    return {
        "ros-graph": Thing(
            "ros-graph",
            "ROS 2 graph (read-only observer)",
            "What the observer sees on the ROS 2 graph it is attached to: nodes, topics with message rates and "
            "freshness, "
            "expected topics, simulation clock, connectivity. It only subscribes; it has no command surface.",
            {
                "summary": Property(
                    "Counts of topics by state and of required topics with problems", obj, graph["summary"]
                ),
                "nodes": Property("Nodes seen on the graph", arr, graph["nodes"]),
                "topics": Property(
                    "Topics with types, publisher counts, rate, age and freshness state", arr, graph["topics"]
                ),
                "expected_topics": Property(
                    "Topics the profile expects, each present, missing, never or stale", arr, graph["expected"]
                ),
                "clock": Property(
                    "Simulation clock (/clock): absent, running, stale, monotonic or not", obj, graph["clock"]
                ),
                "connectivity": Property("Observer process, DDS discovery and graph-poll health", obj, observer),
            },
        ),
        "ros-robot": Thing(
            "ros-robot",
            "Robot state (read-only observer)",
            "Joint states, TF frames, controller states and diagnostics as published on the graph. Values are "
            "shown with "
            "their age; a silent source is reported as silent, never filled in.",
            {
                "joint_states": Property(
                    "Latest /joint_states with per-joint time since last change", obj, robot["joint_states"]
                ),
                "transforms": Property(
                    "TF frames from /tf and /tf_static with parent, pose and age", obj, robot["transforms"]
                ),
                "controllers": Property(
                    "Controller states from the controller manager's list_controllers query", obj, robot["controllers"]
                ),
                "diagnostics": Property("Latest /diagnostics statuses by name", obj, robot["diagnostics"]),
            },
        ),
    }
