"""Decode an MCAP recording into a deterministic playback track (``pap.twin.track/1``).

Nothing here needs ROS: ``mcap-ros2-support`` reads the messages from the file. The track holds only what the messages
contain, on the recording's own clock: the simulation time from ``/clock`` when the recording has one, otherwise the
recorder's log time. Message times are placed on that clock by the latest ``/clock`` value at the moment the recorder
received them (the recorder's log time), never by the message's own header stamp.

Events are observations by a stated rule over those messages. They are not verdicts: the verdict for an episode is the
engine's, shown beside them (see routes.py). The thresholds below are this reader's, labelled as such in every event.
"""

from __future__ import annotations

import bisect
import hashlib
import io
import json
import math
from typing import Any, BinaryIO

from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory

SCHEMA = "pap.twin.track/1"
SAMPLE_S = 0.05  # output spacing of continuous channels (the full-rate data is used for the events)
STOP_SPEED = 0.02  # m/s: at or below this the base is read as stopped
GRACE_S = 1.0  # seconds after the last command within which a stop is read as prompt
NS = 1_000_000_000
TOPICS = ("/clock", "/tf", "/odom", "/joint_states", "/cmd_vel", "/sim/base_cmd_vel")
MAX_MESSAGES = 2_000_000


class RecordingError(ValueError):
    pass


def _yaw(q: Any) -> float:
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def _r(x: float, n: int = 4) -> float:
    return round(x, n) + 0.0  # + 0.0 turns -0.0 into 0.0


def thin(samples: list[tuple[float, Any]]) -> list[tuple[float, Any]]:
    """Keep the first sample, then the first at or after each SAMPLE_S since the last kept, and the last."""
    out: list[tuple[float, Any]] = []
    for s in samples:
        if not out or s[0] - out[-1][0] >= SAMPLE_S:
            out.append(s)
    if samples and out[-1] is not samples[-1]:
        out.append(samples[-1])
    return out


def changes(samples: list[tuple[float, tuple[float, float]]]) -> list[tuple[float, tuple[float, float]]]:
    out: list[tuple[float, tuple[float, float]]] = []
    for s in samples:
        if not out or s[1] != out[-1][1]:
            out.append(s)
    if samples and out[-1] is not samples[-1]:
        out.append(samples[-1])
    return out


def build_track(data: bytes | BinaryIO, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """``data`` is the file's bytes or a seekable binary stream (read in chunks, so a large recording is not loaded)."""
    try:
        reader = make_reader(
            io.BytesIO(data) if isinstance(data, bytes) else data, decoder_factories=[DecoderFactory()]
        )
        stats = reader.get_summary()
    except Exception as e:  # noqa: BLE001 - any parse failure is the uploader's file
        raise RecordingError(f"not a readable MCAP file: {e}") from None
    if stats is None or stats.statistics is None:
        raise RecordingError("the MCAP file has no summary section (it was not closed cleanly): reindex it first")
    counts = {
        stats.channels[cid].topic: n
        for cid, n in stats.statistics.channel_message_counts.items()
        if cid in stats.channels
    }
    total = sum(counts.values())
    if total == 0:
        raise RecordingError("the recording has no messages")
    if total > MAX_MESSAGES:
        raise RecordingError(f"more than {MAX_MESSAGES} messages")
    want = [t for t in TOPICS if t in counts]
    if not [t for t in want if t != "/clock"]:
        raise RecordingError("none of the topics the twin reads were recorded (besides /clock): " + ", ".join(TOPICS))

    clock: list[tuple[int, float]] = []  # (log_ns, sim_s)
    tf: dict[tuple[str, str], list[tuple[int, tuple[float, float, float]]]] = {}
    odom: list[tuple[int, tuple[float, float, float, float, str, str]]] = []
    joints: list[tuple[int, dict[str, float]]] = []
    cmd: dict[str, list[tuple[int, tuple[float, float]]]] = {"/cmd_vel": [], "/sim/base_cmd_vel": []}
    first_ns = None
    last_ns = 0
    for _schema, ch, msg, m in reader.iter_decoded_messages(topics=want):
        t = msg.log_time
        first_ns = t if first_ns is None else first_ns
        last_ns = t
        if ch.topic == "/clock":
            clock.append((t, m.clock.sec + m.clock.nanosec / NS))
        elif ch.topic == "/tf":
            for tr in m.transforms:
                p, c = tr.header.frame_id, tr.child_frame_id
                v = tr.transform
                tf.setdefault((p, c), []).append((t, (v.translation.x, v.translation.y, _yaw(v.rotation))))
        elif ch.topic == "/odom":
            p = m.pose.pose
            odom.append(
                (
                    t,
                    (
                        p.position.x,
                        p.position.y,
                        _yaw(p.orientation),
                        m.twist.twist.linear.x,
                        m.header.frame_id,
                        m.child_frame_id,
                    ),
                )
            )
        elif ch.topic == "/joint_states":
            joints.append((t, {n: v for n, v in zip(m.name, m.position, strict=False)}))
        else:
            cmd[ch.topic].append((t, (m.linear.x, m.angular.z)))
    if first_ns is None:
        raise RecordingError("none of the topics the twin reads were recorded: " + ", ".join(TOPICS))

    clock_ns = [c[0] for c in clock]
    clock_stats: dict[str, Any] = {"backward_jumps": 0, "largest_backward_s": 0.0, "first_backward_at_s": None}
    if clock:
        kind, origin = "sim", clock[0][1]
        # The time axis is the running maximum of /clock: it never moves backwards, so playback stays ordered even if
        # more than one source published /clock. How often it moved backwards is reported (event and clock_stats).
        run: list[float] = []
        for _ns, v in clock:
            if run and v < run[-1] - 1e-9:
                clock_stats["backward_jumps"] += 1
                clock_stats["largest_backward_s"] = max(clock_stats["largest_backward_s"], run[-1] - v)
                if clock_stats["first_backward_at_s"] is None:
                    clock_stats["first_backward_at_s"] = run[-1] - origin
            run.append(max(v, run[-1]) if run else v)
        clock_stats["largest_backward_s"] = _r(clock_stats["largest_backward_s"])
        if clock_stats["first_backward_at_s"] is not None:
            clock_stats["first_backward_at_s"] = _r(clock_stats["first_backward_at_s"])

        def at(ns: int) -> float:
            i = bisect.bisect_right(clock_ns, ns) - 1
            return max(run[max(i, 0)] - origin, 0.0)

        span = max(run[-1] - origin, 0.0)
    else:
        kind, origin = "log", first_ns / NS

        def at(ns: int) -> float:
            return (ns - first_ns) / NS

        span = (last_ns - first_ns) / NS

    # The base pose: the /tf transform with the most samples that ends in base_footprint (else the most samples);
    # without /tf, the odometry pose.
    pose: list[tuple[float, tuple[float, float, float]]] = []
    frames: dict[str, str | None] = {"parent": None, "child": None, "source": None}
    if tf:
        key = max(tf, key=lambda k: (k[1] == "base_footprint", len(tf[k]), k))
        pose = [(at(t), v) for t, v in tf[key]]
        frames = {"parent": key[0], "child": key[1], "source": "/tf"}
    elif odom:
        pose = [(at(t), (v[0], v[1], v[2])) for t, v in odom]
        frames = {"parent": odom[0][1][4], "child": odom[0][1][5], "source": "/odom"}
    speed = [(at(t), v[3]) for t, v in odom]
    names: list[str] = []
    for _, d in joints:
        for n in d:
            if n not in names:
                names.append(n)
    jt = thin([(at(t), d) for t, d in joints])
    commands = {k: [(at(t), v) for t, v in s] for k, s in cmd.items()}

    events = _events(commands, speed, pose, summary, at, clock_stats, span)
    jstats = {
        n: {
            "messages": sum(1 for _, d in joints if n in d),
            "min": _r(min(d[n] for _, d in joints if n in d), 5),
            "max": _r(max(d[n] for _, d in joints if n in d), 5),
        }
        for n in names
    }
    travelled = math.hypot(pose[-1][1][0] - pose[0][1][0], pose[-1][1][1] - pose[0][1][1]) if len(pose) > 1 else 0.0
    for n, st in jstats.items():
        if st["messages"] > 1 and st["min"] == st["max"] and travelled > 0.05:
            events.append(
                {
                    "t": _r(jt[0][0]),
                    "kind": "joint_constant",
                    "severity": "warning",
                    "title": f"{n} reports a constant position",
                    "rule": "Every /joint_states message reports the same position for this joint while the base "
                    "pose changes by more than 0.05 m. The wheel is drawn at that constant angle; no spin is inferred.",
                    "topics": ["/joint_states", "/tf"],
                    "detail": {"position_rad": st["min"], "messages": st["messages"], "base_travel_m": _r(travelled)},
                }
            )
    events.sort(key=lambda e: (e["t"], e["kind"], ",".join(e["topics"])))
    for i, item in enumerate(events, 1):
        item["id"] = f"ev-{i}"
    track: dict[str, Any] = {
        "schema": SCHEMA,
        "clock": kind,
        "start_clock_s": _r(origin, 6),
        "duration_s": _r(span),
        "frames": frames,
        "counts": dict(sorted(counts.items())),
        "base": _cols(thin(pose), ("x", "y", "yaw")),
        "joints": {
            "names": names,
            "t": [_r(t) for t, _ in jt],
            "position": [[_r(d[n], 5) if n in d else None for n in names] for _, d in jt],
            "stats": jstats,
        },
        "odom_speed": {"t": [_r(t) for t, _ in thin(speed)], "linear_x": [_r(v, 4) for _, v in thin(speed)]},
        "commands": {
            k.strip("/").replace("/", "_"): {
                "topic": k,
                "messages": len(commands[k]),
                "t": [_r(t) for t, _ in changes(commands[k])],
                "linear_x": [_r(v[0], 4) for _, v in changes(commands[k])],
                "angular_z": [_r(v[1], 4) for _, v in changes(commands[k])],
            }
            for k in cmd
            if commands[k]
        },
        "clock_stats": clock_stats,
        "events": events,
        "limits": {"stop_speed_m_s": STOP_SPEED, "grace_s": GRACE_S, "sample_s": SAMPLE_S},
    }
    return track


def _cols(samples: list[tuple[float, tuple[float, ...]]], names: tuple[str, ...]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {"t": [_r(t) for t, _ in samples]}
    for i, n in enumerate(names):
        out[n] = [_r(v[i], 5) for _, v in samples]
    return out


def canonical(track: dict[str, Any]) -> bytes:
    return json.dumps(track, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def track_sha256(track: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical(track)).hexdigest()


def _events(
    commands: dict[str, list[tuple[float, tuple[float, float]]]],
    speed: list[tuple[float, float]],
    pose: list[tuple[float, tuple[float, float, float]]],
    summary: dict[str, Any] | None,
    at: Any,
    clock_stats: dict[str, Any],
    span: float,
) -> list[dict[str, Any]]:
    ev: list[dict[str, Any]] = []

    def add(
        t: float, kind: str, severity: str, title: str, rule: str, topics: list[str], detail: dict[str, Any]
    ) -> None:
        ev.append(
            {
                "t": _r(t),
                "kind": kind,
                "severity": severity,
                "title": title,
                "rule": rule,
                "topics": topics,
                "detail": detail,
            }
        )

    cv = commands["/cmd_vel"]
    moving = [s for s in cv if s[1] != (0.0, 0.0)]
    if moving:
        add(
            moving[0][0],
            "command_first",
            "info",
            "First motion command received",
            "The first /cmd_vel message with a non-zero linear or angular velocity.",
            ["/cmd_vel"],
            {"linear_x": _r(moving[0][1][0]), "angular_z": _r(moving[0][1][1])},
        )
    if cv:
        t_last, last = cv[-1]
        add(
            t_last,
            "command_last",
            "info",
            "Last command received",
            "The last message on /cmd_vel in the recording; nothing follows it.",
            ["/cmd_vel"],
            {"messages": len(cv), "linear_x": _r(last[0]), "angular_z": _r(last[1])},
        )
        _after_last_command(ev, add, t_last, speed, pose, commands.get("/sim/base_cmd_vel", []), span)
    if clock_stats["backward_jumps"]:
        add(
            clock_stats["first_backward_at_s"],
            "clock_not_monotonic",
            "warning",
            "The recorded clock moved backwards",
            "A /clock message with a time earlier than one already received. Playback uses the running maximum, so the "
            "times of other messages in the affected window are approximate.",
            ["/clock"],
            {"backward_jumps": clock_stats["backward_jumps"], "largest_backward_s": clock_stats["largest_backward_s"]},
        )
    if summary:
        for tp in summary.get("topics", []):
            for iv in tp.get("stale_intervals", []):
                a, b = at(int(iv["start_ns"])), at(int(iv["end_ns"]))
                add(
                    a,
                    "stale_interval",
                    "warning",
                    f"{tp['name']} went silent",
                    "A gap between consecutive messages longer than the stale threshold in the bag summary.",
                    [tp["name"]],
                    {"from_s": _r(a), "to_s": _r(b), "length_s": iv.get("length_s")},
                )
    ev.sort(key=lambda e: (e["t"], e["kind"], ",".join(e["topics"])))
    for i, e in enumerate(ev, 1):
        e["id"] = f"ev-{i}"
    return ev


def _after_last_command(
    ev: list[dict[str, Any]],
    add: Any,
    t_last: float,
    speed: list[tuple[float, float]],
    pose: list[tuple[float, tuple[float, float, float]]],
    applied: list[tuple[float, tuple[float, float]]],
    span: float,
) -> None:
    rule_motion = (
        f"After the last /cmd_vel message: the base is read as stopped when |/odom linear.x| is at most "
        f"{STOP_SPEED} m/s and stays there to the end of the recording; a stop later than {GRACE_S} s is not prompt. "
        "These thresholds are this reader's, not a contract; the contract verdict is the engine's."
    )
    after = [s for s in speed if s[0] >= t_last]
    if not after:
        return
    stop_t = None
    for i, (t, _v) in enumerate(after):
        if all(abs(x[1]) <= STOP_SPEED for x in after[i:]):
            stop_t = t
            break
    at_cmd = [p for p in pose if p[0] <= t_last]
    p0 = at_cmd[-1][1] if at_cmd else (pose[0][1] if pose else None)
    end = [p for p in pose if stop_t is None or p[0] <= stop_t]
    p1 = end[-1][1] if end else None
    travel = _r(math.hypot(p1[0] - p0[0], p1[1] - p0[1]), 4) if p0 and p1 else None
    if stop_t is not None and stop_t - t_last <= GRACE_S:
        add(
            stop_t,
            "motion_stopped",
            "info",
            "Base stopped after the last command",
            rule_motion,
            ["/odom", "/cmd_vel"],
            {"seconds_after_last_command": _r(stop_t - t_last), "travel_after_last_command_m": travel},
        )
    elif stop_t is not None:
        add(
            stop_t,
            "motion_stopped_late",
            "problem",
            "Base stopped late after the last command",
            rule_motion,
            ["/odom", "/cmd_vel"],
            {"seconds_after_last_command": _r(stop_t - t_last), "travel_after_last_command_m": travel},
        )
    else:
        t_flag = min(t_last + GRACE_S, span)
        add(
            t_flag,
            "motion_continues",
            "problem",
            "Base still moving after the last command",
            rule_motion,
            ["/odom", "/cmd_vel"],
            {
                "seconds_after_last_command_at_end": _r(max(span - t_last, 0.0)),
                "speed_at_end_m_s": _r(after[-1][1]),
                "travel_after_last_command_m": travel,
            },
        )
    if applied:
        zero = next((t for t, v in applied if t >= t_last and v == (0.0, 0.0)), None)
        rule = (
            "The first /sim/base_cmd_vel message at or after the last /cmd_vel message whose velocities are both zero."
        )
        if zero is not None:
            add(
                zero,
                "applied_command_zero",
                "info",
                "Applied command reached zero",
                rule,
                ["/sim/base_cmd_vel"],
                {"seconds_after_last_command": _r(zero - t_last)},
            )
        else:
            add(
                span,
                "applied_command_never_zero",
                "problem",
                "Applied command never reached zero",
                rule,
                ["/sim/base_cmd_vel"],
                {},
            )
