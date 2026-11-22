import { describe, expect, it } from "vitest";
import fix from "./fixtures/openamr-fix.track.json";
import main from "./fixtures/openamr-main.track.json";
import snapshot from "../../../../runtimes/ros-observer/tests/fixtures/openamr-upperbody-mock.snapshot.json";
import {
  angleAt,
  drivenJoints,
  holdAt,
  lerpAt,
  linkDetail,
  matchJoints,
  nextEvent,
  observerBasePose,
  observerJoints,
  observerMode,
  sampleAt,
  yawOf,
  type Structure,
  type Track,
} from "./twin";

const FIX = fix as unknown as Track;
const MAIN = main as unknown as Track;

describe("interpolation", () => {
  it("clamps to the ends and is linear between samples", () => {
    expect(lerpAt([], [], 1)).toBeNull();
    expect(lerpAt([1, 3], [10, 30], 0)).toBe(10);
    expect(lerpAt([1, 3], [10, 30], 2)).toBe(20);
    expect(lerpAt([1, 3], [10, 30], 9)).toBe(30);
  });
  it("turns an angle the short way round", () => {
    const a = angleAt([0, 1], [Math.PI - 0.1, -Math.PI + 0.1], 0.5) as number;
    expect(Math.abs(Math.abs(a) - Math.PI)).toBeLessThan(1e-9);
  });
  it("holds a command until the next message and knows nothing before the first", () => {
    expect(holdAt([1, 2], [5, 0], 0.5)).toBeNull();
    expect(holdAt([1, 2], [5, 0], 1.5)).toBe(5);
    expect(holdAt([1, 2], [5, 0], 2)).toBe(0);
  });
  it("reads yaw from a quaternion", () => {
    expect(yawOf([0, 0, 0, 1])).toBe(0);
    expect(yawOf([0, 0, Math.sin(Math.PI / 4), Math.cos(Math.PI / 4)])).toBeCloseTo(Math.PI / 2);
  });
});

describe("a real recorded track", () => {
  it("starts at the origin and ends where the recording says the base was", () => {
    const s0 = sampleAt(FIX, 0);
    expect(s0.pose?.x).toBeCloseTo(0, 3);
    const end = sampleAt(FIX, 1e6); // clamped to the end of the recording
    expect(end.t).toBe(FIX.duration_s);
    expect(end.pose?.x).toBeCloseTo(FIX.base.x[FIX.base.x.length - 1]!, 6);
  });
  it("moves the base between samples and never past the recorded extremes", () => {
    let prev = -1;
    for (let t = 0; t <= FIX.duration_s; t += 0.25) {
      const x = sampleAt(FIX, t).pose!.x;
      expect(x).toBeGreaterThanOrEqual(prev - 1e-9); // the base only drives forward in this run
      prev = x;
    }
    expect(prev).toBeLessThanOrEqual(Math.max(...FIX.base.x) + 1e-9);
  });
  it("shows the command in force: moving while commanded, zero once the applied command stops", () => {
    const last = FIX.events.find((e) => e.kind === "command_last")!;
    expect(sampleAt(FIX, last.t - 0.1).commands["cmd_vel"]?.linear_x).toBe(0.2);
    const zero = FIX.events.find((e) => e.kind === "applied_command_zero")!;
    expect(sampleAt(FIX, zero.t + 0.05).commands["sim_base_cmd_vel"]?.linear_x).toBe(0);
    expect(sampleAt(FIX, 0.001).commands["cmd_vel"]).toBeNull(); // nothing commanded yet
  });
  it("the pre-fix base is still moving when the recording ends; the fixed one has stopped", () => {
    expect(sampleAt(MAIN, MAIN.duration_s).speed).toBeGreaterThan(0.15);
    expect(Math.abs(sampleAt(FIX, FIX.duration_s).speed as number)).toBeLessThan(FIX.limits.stop_speed_m_s);
  });
  it("reports wheel joints with the constant 0 the recording contains: no spin is invented", () => {
    const j = sampleAt(FIX, 5).joints;
    expect(j["left_wheel_joint"]).toBe(0);
    expect(FIX.joints.stats["left_wheel_joint"]).toEqual({ messages: 111, min: 0, max: 0 });
  });
  it("steps through the recording's events in time order", () => {
    const first = nextEvent(MAIN.events, -1, 1)!;
    expect(first.t).toBe(MAIN.events[0]!.t);
    let n = 0;
    for (let e = first; e && n < 50; e = nextEvent(MAIN.events, e.t, 1)!, n++);
    expect(n).toBeGreaterThanOrEqual(MAIN.events.filter((e, i, a) => i === 0 || e.t !== a[i - 1]!.t).length);
    expect(nextEvent(MAIN.events, MAIN.duration_s + 1, 1)).toBeNull();
    expect(nextEvent(MAIN.events, 0, -1)).toBeNull();
  });
});

const STRUCT: Structure = {
  root: "base",
  links: [{ name: "base", visuals: [] }, { name: "wheel", visuals: [] }, { name: "lidar", visuals: [] }],
  joints: [
    { name: "w", type: "continuous", parent: "base", child: "wheel", xyz: [0, 0, 0], rpy: [0, 0, 0], axis: [0, 1, 0], limit: null },
    { name: "l", type: "fixed", parent: "base", child: "lidar", xyz: [0, 0, 0], rpy: [0, 0, 0], axis: null, limit: null },
  ],
  sensors: [{ name: "lidar_sensor", type: "gpu_lidar", link: "lidar", topic: "/scan", frame: "lidar", update_rate_hz: 10 }],
  controllers: [{ name: "gz::sim::systems::DiffDrive", plugin: "diff", params: { left_joint: "w", topic: "/cmd_vel" } }],
};

describe("what the model says about a link", () => {
  it("finds the parent joint, the controller that drives it and the sensors on the link", () => {
    expect(drivenJoints(STRUCT.controllers[0]!)).toEqual(["w"]);
    const wheel = linkDetail(STRUCT, "wheel");
    expect(wheel.parent?.name).toBe("w");
    expect(wheel.drivers.map((c) => c.name)).toEqual(["gz::sim::systems::DiffDrive"]);
    expect(linkDetail(STRUCT, "lidar").sensors.map((s) => s.name)).toEqual(["lidar_sensor"]);
    expect(linkDetail(STRUCT, "base").children.map((j) => j.name)).toEqual(["w", "l"]);
    expect(linkDetail(STRUCT, "base").parent).toBeNull();
  });
});

type Snap = { things: Record<string, Record<string, Record<string, unknown>>> };
const SNAP = snapshot as unknown as Snap;
const reads = {
  connectivity: SNAP.things["ros-graph"]!.connectivity!,
  joint_states: SNAP.things["ros-robot"]!.joint_states!,
  transforms: SNAP.things["ros-robot"]!.transforms!,
};

describe("an observed ROS graph (the real recorded snapshot of the upper-body mock)", () => {
  it("is simulated when its poll is fresh and its environment is simulated, live when physical", () => {
    expect(observerMode("simulated", reads, false).mode).toBe("simulated");
    expect(observerMode("physical", reads, false).mode).toBe("live");
  });
  it("is recorded whenever the observer says it replays a snapshot, in any kind of environment", () => {
    const replay = { ...reads, connectivity: { ...reads.connectivity, recorded_not_live: true } };
    expect(observerMode("simulated", replay, false).mode).toBe("recorded");
    expect(observerMode("physical", replay, false).mode).toBe("recorded");
  });
  it("is disconnected when unreachable, when the graph has not been polled, or when no joint states are published", () => {
    expect(observerMode("simulated", {}, true).mode).toBe("disconnected");
    expect(observerMode("simulated", { ...reads, connectivity: { ...reads.connectivity, last_graph_poll_age_s: 30 } }, false).mode).toBe("disconnected");
    expect(observerMode("simulated", { ...reads, joint_states: { sources: [] } }, false).mode).toBe("disconnected");
  });
  it("reads the joints it reports and says how many exist in the platform model: none do, and none are guessed", () => {
    const joints = observerJoints(reads.joint_states);
    expect(Object.keys(joints).length).toBe(17);
    const { matched, unmatched } = matchJoints(["left_wheel_joint", "right_wheel_joint"], Object.keys(joints));
    expect(matched).toEqual([]);
    expect(unmatched.length).toBe(17);
    expect(matchJoints(["lift_joint", "x"], Object.keys(joints)).matched).toEqual(["lift_joint"]);
  });
  it("finds a base pose only when the named frame is in the TF the observer saw", () => {
    expect(observerBasePose(reads.transforms, "odom", "base_footprint")).toBeNull();
    const pose = observerBasePose({ frames: [{ parent: "odom", child: "base_footprint", translation: [1, 2, 0], rotation: [0, 0, 0, 1], static: false }] }, "odom", "base_footprint");
    expect(pose).toEqual({ x: 1, y: 2, yaw: 0 });
  });
});
