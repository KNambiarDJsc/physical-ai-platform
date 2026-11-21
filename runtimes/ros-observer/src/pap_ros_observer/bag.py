"""Summarise a rosbag2 recording (MCAP or SQLite3) as deterministic JSON: what was recorded, when, where it went silent.

Needs rosbag2_py (ROS 2). Nothing is interpolated: a gap is a gap and is listed with its start and end. The same bag and
identity give byte-identical output (no wall clock, sorted keys, file digests). The log time of a message is the time
the RECORDER received it (its wall clock); header stamps and the simulation clock are separate facts.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from itertools import pairwise
from pathlib import Path
from typing import Any

from rclpy.serialization import deserialize_message
from rosbag2_py import ConverterOptions, SequentialReader, StorageOptions
from rosgraph_msgs.msg import Clock

from .model import STALE_MIN_S, STALE_PERIODS

SCHEMA = "pap.ros.bag-summary/1"
IDENTITY_FILE = "pap-run-identity.json"
NS = 1_000_000_000


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _storage_id(bag: Path) -> str:
    meta = bag / "metadata.yaml"
    m = re.search(r"storage_identifier:\s*(\w+)", meta.read_text(encoding="utf-8")) if meta.is_file() else None
    if m:
        return m.group(1)
    return "mcap" if list(bag.glob("*.mcap")) else "sqlite3"


def summarize_bag(bag: Path, identity: str | None = None, expected: list[str] | None = None) -> dict[str, Any]:
    bag = Path(bag)
    sid = _storage_id(bag)
    reader = SequentialReader()
    reader.open(StorageOptions(uri=str(bag), storage_id=sid), ConverterOptions("cdr", "cdr"))
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    times: dict[str, list[int]] = {n: [] for n in types}
    clock: list[tuple[int, float]] = []
    while reader.has_next():
        topic, data, t_ns = reader.read_next()
        times[topic].append(int(t_ns))
        if topic == "/clock" and types.get(topic) == "rosgraph_msgs/msg/Clock":
            c = deserialize_message(data, Clock)
            clock.append((int(t_ns), c.clock.sec + c.clock.nanosec / NS))

    all_times = [t for ts in times.values() for t in ts]
    t0, t1 = (min(all_times), max(all_times)) if all_times else (0, 0)
    topics = []
    for name in sorted(types):
        ts = sorted(times[name])
        entry: dict[str, Any] = {"name": name, "type": types[name], "messages": len(ts)}
        if not ts:
            entry["state"] = "empty"
        else:
            gaps = [b - a for a, b in pairwise(ts)]
            med = statistics.median(gaps) / NS if gaps else None
            stale_after = max(STALE_MIN_S, STALE_PERIODS * med) if med else STALE_MIN_S
            entry |= {
                "state": "recorded",
                "first_log_ns": ts[0],
                "last_log_ns": ts[-1],
                "duration_s": round((ts[-1] - ts[0]) / NS, 6),
                "rate_hz": round(1 / med, 3) if med else None,
                "max_gap_s": round(max(gaps) / NS, 6) if gaps else 0.0,
                "stale_after_s": round(stale_after, 3),
                # Intervals where the topic was silent for longer than the observer's staleness rule, as recorded.
                "stale_intervals": [
                    {"start_ns": a, "end_ns": b, "length_s": round((b - a) / NS, 6)}
                    for a, b in pairwise(ts)
                    if (b - a) / NS > stale_after
                ],
                # Silence at the ends of the recording: the topic stopped (or had not started) while others went on.
                "silent_before_first_s": round((ts[0] - t0) / NS, 6),
                "silent_after_last_s": round((t1 - ts[-1]) / NS, 6),
            }
        topics.append(entry)

    expect = sorted(set(expected or []))
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "bag": bag.name,
        "storage": sid,
        "log_time_note": "log time is the recorder's wall clock at receipt, not the message stamp or the sim clock",
        "recording": {
            "first_log_ns": t0,
            "last_log_ns": t1,
            "duration_s": round((t1 - t0) / NS, 6),
            "messages": len(all_times),
            "topics": len(types),
        },
        "topics": topics,
        "expected_topics": [
            {"name": n, "state": "missing" if n not in types else ("empty" if not times[n] else "recorded")}
            for n in expect
        ],
        "files": [
            {"name": p.name, "sha256": _sha256(p), "bytes": p.stat().st_size}
            for p in sorted(bag.iterdir())
            if p.is_file() and p.name != IDENTITY_FILE
        ],
    }
    out["clock"] = _clock_summary(clock)
    ident = (
        Path(identity)
        if identity
        else next((c for c in (bag / IDENTITY_FILE, bag.parent / IDENTITY_FILE) if c.is_file()), bag / IDENTITY_FILE)
    )
    out["identity"] = json.loads(ident.read_text(encoding="utf-8")) if ident.is_file() else None
    return out


def _clock_summary(clock: list[tuple[int, float]]) -> dict[str, Any]:
    if not clock:
        return {"state": "absent", "messages": 0}
    back = [(a[1] - b[1]) for a, b in pairwise(clock) if b[1] < a[1]]
    wall = (clock[-1][0] - clock[0][0]) / NS
    sim = clock[-1][1] - clock[0][1]
    return {
        "state": "recorded",
        "messages": len(clock),
        "sim_first_s": clock[0][1],
        "sim_last_s": clock[-1][1],
        "sim_span_s": round(sim, 6),
        "recorder_wall_span_s": round(wall, 6),
        "real_time_factor": round(sim / wall, 4) if wall > 0 else None,
        "monotonic": not back,
        "backward_jumps": len(back),
        "largest_backward_s": round(max(back), 6) if back else 0.0,
    }
