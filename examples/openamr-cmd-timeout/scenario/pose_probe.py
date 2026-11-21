"""Watch the robot's Gazebo world pose (gz-transport, simulation time from the message stamps) while a
/cmd_vel publisher drives it, SIGKILL the publisher, and record how far the base travels afterwards."""

import json
import math
import os
import signal
import sys
import threading
import time

from gz.msgs10.pose_v_pb2 import Pose_V
from gz.transport13 import Node

PUB_PID, OUT = int(sys.argv[1]), sys.argv[2]
MODEL = "openamrobot"
lock, samples = threading.Lock(), []  # (sim_t, x, y)


def on_poses(msg):
    t = msg.header.stamp.sec + msg.header.stamp.nsec * 1e-9
    for p in msg.pose:
        if p.name == MODEL:
            with lock:
                samples.append((t, p.position.x, p.position.y))


def sim_now():
    with lock:
        return samples[-1][0] if samples else None


def wait_sim(t_target, wall_limit=120):
    end = time.time() + wall_limit
    while time.time() < end:
        s = sim_now()
        if s is not None and s >= t_target:
            return
        time.sleep(0.02)
    raise TimeoutError(f"simulation time did not reach {t_target}")


def travel(t0, t1):
    with lock:
        pts = [(x, y) for t, x, y in samples if t0 <= t <= t1]
    return math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) if len(pts) > 1 else float("nan")


node = Node()
assert node.subscribe(Pose_V, "/world/walled_world/dynamic_pose/info", on_poses)
end = time.time() + 60
while sim_now() is None and time.time() < end:
    time.sleep(0.1)
t_start = sim_now()
wait_sim(t_start + 4.0)
t_kill = sim_now()
os.kill(PUB_PID, signal.SIGKILL)
wait_sim(t_kill + 5.0)
t_end = sim_now()
res = {
    "driven_before_kill_m": travel(t_start, t_kill),
    "travel_after_kill_m": travel(t_kill, t_end),
    "travel_last_2s_m": travel(t_end - 2.0, t_end),
    "samples": len(samples),
    "t_kill_sim": t_kill,
}
print(json.dumps(res, indent=1))
with open(OUT, "w") as f:
    json.dump({"result": res, "samples": samples}, f)
