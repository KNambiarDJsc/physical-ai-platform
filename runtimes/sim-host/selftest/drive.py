"""``selftest-drive``: a kinematic point base, to exercise the whole experiment journey without a simulator.

NOT a simulator and not physics. A differential base follows its last velocity command exactly (no dynamics); a command
source publishes at 10 Hz for ``drive_s`` and then stops (the "command loss"). With ``stop_on_command_loss`` the base
stops once no command arrived for ``command_timeout_s``; without it, the base keeps its last command. The seed moves the
moment of command loss by up to 0.2 s. Every number in the recording and the measurements is computed by this stated
rule; nothing is replayed from another run. The MCAP is written with the same library the platform reads it with.
"""

from __future__ import annotations

import io
import math
import random
from pathlib import Path
from typing import Any

from mcap_ros2.writer import Writer

RATE_HZ = 50
CMD_HZ = 10
OBSERVE_S = 3.0  # recording continues this long after the command loss
WHEEL_RADIUS_M = 0.1
SEP = "=" * 80 + "\n"


def _msg(*parts: str) -> str:
    return ("\n" + SEP).join(parts)


TIME = "MSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec"
HEADER = "MSG: std_msgs/Header\nbuiltin_interfaces/Time stamp\nstring frame_id"
VEC3 = "MSG: geometry_msgs/Vector3\nfloat64 x\nfloat64 y\nfloat64 z"
QUAT = "MSG: geometry_msgs/Quaternion\nfloat64 x 0\nfloat64 y 0\nfloat64 z 0\nfloat64 w 1"
POINT = "MSG: geometry_msgs/Point\nfloat64 x\nfloat64 y\nfloat64 z"
TWIST_BODY = "Vector3 linear\nVector3 angular"

DEFS = {
    "rosgraph_msgs/msg/Clock": _msg("builtin_interfaces/Time clock", TIME),
    "geometry_msgs/msg/Twist": _msg(TWIST_BODY, VEC3),
    "sensor_msgs/msg/JointState": _msg(
        "std_msgs/Header header\nstring[] name\nfloat64[] position\nfloat64[] velocity\nfloat64[] effort", HEADER, TIME
    ),
    "tf2_msgs/msg/TFMessage": _msg(
        "geometry_msgs/TransformStamped[] transforms",
        "MSG: geometry_msgs/TransformStamped\nstd_msgs/Header header\nstring child_frame_id\nTransform transform",
        "MSG: geometry_msgs/Transform\nVector3 translation\nQuaternion rotation",
        VEC3,
        QUAT,
        HEADER,
        TIME,
    ),
    "nav_msgs/msg/Odometry": _msg(
        "std_msgs/Header header\nstring child_frame_id\ngeometry_msgs/PoseWithCovariance pose\n"
        "geometry_msgs/TwistWithCovariance twist",
        "MSG: geometry_msgs/PoseWithCovariance\nPose pose\nfloat64[36] covariance",
        "MSG: geometry_msgs/Pose\nPoint position\nQuaternion orientation",
        POINT,
        QUAT,
        "MSG: geometry_msgs/TwistWithCovariance\nTwist twist\nfloat64[36] covariance",
        "MSG: geometry_msgs/Twist\n" + TWIST_BODY,
        VEC3,
        HEADER,
        TIME,
    ),
}


def _stamp(t: float) -> dict[str, int]:
    sec = int(t)
    return {"sec": sec, "nanosec": round((t - sec) * 1e9) % 1_000_000_000}


def run(p: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    speed = float(p.get("speed_mps", 0.3))
    drive_s = float(p.get("drive_s", 2.0))
    timeout_s = float(p.get("command_timeout_s", 0.5))
    stops = bool(p["stop_on_command_loss"])
    seed = p.get("seed")
    loss_t = drive_s + (random.Random(int(seed)).uniform(0.0, 0.2) if seed is not None else 0.0)
    end_t = loss_t + OBSERVE_S

    buf = io.BytesIO()
    w = Writer(buf)
    sch = {name: w.register_msgdef(name, text) for name, text in DEFS.items()}
    x = 0.0
    v = 0.0
    wheel = 0.0
    last_cmd_t: float | None = None
    x_at_loss: float | None = None
    dt = 1.0 / RATE_HZ
    next_cmd = 0.0
    zero36 = [0.0] * 36
    steps = round(end_t * RATE_HZ)
    for i in range(steps + 1):
        t = i * dt
        ns = round(t * 1e9)
        if t + 1e-9 >= next_cmd and t < loss_t:
            last_cmd_t = t
            v = speed
            w.write_message(
                "/cmd_vel",
                sch["geometry_msgs/msg/Twist"],
                {"linear": {"x": speed, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}},
                log_time=ns,
                publish_time=ns,
            )
            next_cmd += 1.0 / CMD_HZ
        if x_at_loss is None and t >= loss_t:
            x_at_loss = x
        if stops and last_cmd_t is not None and t - last_cmd_t > timeout_s:
            v = 0.0
        w.write_message("/clock", sch["rosgraph_msgs/msg/Clock"], {"clock": _stamp(t)}, log_time=ns, publish_time=ns)
        hdr = {"stamp": _stamp(t), "frame_id": "odom"}
        quat = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
        w.write_message(
            "/tf",
            sch["tf2_msgs/msg/TFMessage"],
            {
                "transforms": [
                    {
                        "header": hdr,
                        "child_frame_id": "base_footprint",
                        "transform": {"translation": {"x": x, "y": 0.0, "z": 0.0}, "rotation": quat},
                    }
                ]
            },
            log_time=ns,
            publish_time=ns,
        )
        w.write_message(
            "/odom",
            sch["nav_msgs/msg/Odometry"],
            {
                "header": hdr,
                "child_frame_id": "base_footprint",
                "pose": {"pose": {"position": {"x": x, "y": 0.0, "z": 0.0}, "orientation": quat}, "covariance": zero36},
                "twist": {
                    "twist": {"linear": {"x": v, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}},
                    "covariance": zero36,
                },
            },
            log_time=ns,
            publish_time=ns,
        )
        w.write_message(
            "/joint_states",
            sch["sensor_msgs/msg/JointState"],
            {
                "header": {"stamp": _stamp(t), "frame_id": ""},
                "name": ["left_wheel_joint", "right_wheel_joint"],
                "position": [wheel, wheel],
                "velocity": [v / WHEEL_RADIUS_M] * 2,
                "effort": [],
            },
            log_time=ns,
            publish_time=ns,
        )
        x += v * dt
        wheel = math.remainder(wheel + v / WHEEL_RADIUS_M * dt, 2 * math.pi)
    w.finish()
    (run_dir / "drive.mcap").write_bytes(buf.getvalue())
    before = x_at_loss if x_at_loss is not None else x
    return {
        "measurements": {
            "travel_after_kill_m": round(x - before, 6),
            "driven_before_kill_m": round(before, 6),
        },
        "artifacts": {"recording": "drive.mcap"},
        "identity": {
            "kind": "selftest",
            "model": "kinematic point base (no dynamics)",
            "stop_on_command_loss": stops,
            "command_loss_at_s": round(loss_t, 6),
            "seed": seed,
        },
    }
