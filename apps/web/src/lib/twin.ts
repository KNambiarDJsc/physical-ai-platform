/**
 * Playback and observation logic for the digital twin. Pure functions, no React, no three.js.
 *
 * A track is what the API decoded from a recording; this module only looks values up in it (interpolating poses and
 * joint angles between samples, holding commands between messages). It computes no statistic and decides no verdict.
 */

export type Mode = "live" | "recorded" | "simulated" | "disconnected";

export type TwinEvent = {
  id: string;
  t: number;
  kind: string;
  severity: "info" | "warning" | "problem";
  title: string;
  rule: string;
  topics: string[];
  detail: Record<string, unknown>;
};

export type Series = { topic: string; messages: number; t: number[]; linear_x: number[]; angular_z: number[] };

export type Track = {
  schema: string;
  clock: "sim" | "log";
  start_clock_s: number;
  duration_s: number;
  frames: { parent: string | null; child: string | null; source: string | null };
  counts: Record<string, number>;
  base: { t: number[]; x: number[]; y: number[]; yaw: number[] };
  joints: {
    names: string[];
    t: number[];
    position: (number | null)[][];
    stats: Record<string, { messages: number; min: number; max: number }>;
  };
  odom_speed: { t: number[]; linear_x: number[] };
  commands: Record<string, Series>;
  clock_stats: { backward_jumps: number; largest_backward_s: number; first_backward_at_s: number | null };
  events: TwinEvent[];
  limits: { stop_speed_m_s: number; grace_s: number; sample_s: number };
};

export type Pose = { x: number; y: number; yaw: number };

export type Sample = {
  t: number;
  pose: Pose | null;
  joints: Record<string, number | null>;
  speed: number | null;
  commands: Record<string, { linear_x: number; angular_z: number } | null>;
};

/** An element of a series the caller has already bounds-checked. */
const n = (a: readonly number[], i: number): number => a[i] ?? Number.NaN;

/** Index of the last element <= v, or -1 when every element is greater. */
export function lastAtOrBefore(ts: number[], v: number): number {
  let lo = 0;
  let hi = ts.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (n(ts, mid) <= v) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans;
}

/** Linear interpolation, clamped to the first and last sample; null for an empty series. */
export function lerpAt(ts: number[], vs: number[], t: number): number | null {
  if (ts.length === 0) return null;
  const i = lastAtOrBefore(ts, t);
  if (i < 0) return n(vs, 0);
  if (i >= ts.length - 1) return n(vs, ts.length - 1);
  const span = n(ts, i + 1) - n(ts, i);
  const f = span > 0 ? (t - n(ts, i)) / span : 0;
  return n(vs, i) + (n(vs, i + 1) - n(vs, i)) * f;
}

/** Interpolation of an angle along the shorter way round. */
export function angleAt(ts: number[], vs: number[], t: number): number | null {
  if (ts.length === 0) return null;
  const i = lastAtOrBefore(ts, t);
  if (i < 0) return n(vs, 0);
  if (i >= ts.length - 1) return n(vs, ts.length - 1);
  const span = n(ts, i + 1) - n(ts, i);
  const f = span > 0 ? (t - n(ts, i)) / span : 0;
  let d = n(vs, i + 1) - n(vs, i);
  d = Math.atan2(Math.sin(d), Math.cos(d));
  return n(vs, i) + d * f;
}

/** The value in force at t: the last message at or before t, or null before the first one (nothing was commanded yet). */
export function holdAt(ts: number[], vs: number[], t: number): number | null {
  const i = lastAtOrBefore(ts, t);
  return i < 0 ? null : n(vs, i);
}

export function sampleAt(track: Track, t: number): Sample {
  const at = Math.min(Math.max(t, 0), track.duration_s);
  const b = track.base;
  const x = lerpAt(b.t, b.x, at);
  const y = lerpAt(b.t, b.y, at);
  const yaw = angleAt(b.t, b.yaw, at);
  const joints: Record<string, number | null> = {};
  track.joints.names.forEach((name, col) => {
    const ts: number[] = [];
    const vs: number[] = [];
    track.joints.t.forEach((jt, row) => {
      const v = track.joints.position[row]?.[col] ?? null;
      if (v !== null) {
        ts.push(jt);
        vs.push(v);
      }
    });
    joints[name] = lerpAt(ts, vs, at);
  });
  const commands: Sample["commands"] = {};
  for (const [key, s] of Object.entries(track.commands)) {
    const lx = holdAt(s.t, s.linear_x, at);
    const az = holdAt(s.t, s.angular_z, at);
    commands[key] = lx === null || az === null ? null : { linear_x: lx, angular_z: az };
  }
  return {
    t: at,
    pose: x === null || y === null || yaw === null ? null : { x, y, yaw },
    joints,
    speed: lerpAt(track.odom_speed.t, track.odom_speed.linear_x, at),
    commands,
  };
}

/** Joint angles as a lookup for the model: only names with a value. */
export function jointValues(sample: Sample): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(sample.joints)) if (v !== null) out[k] = v;
  return out;
}

export function nextEvent(events: TwinEvent[], t: number, dir: 1 | -1): TwinEvent | null {
  const eps = 1e-6;
  if (dir === 1) return events.find((e) => e.t > t + eps) ?? null;
  return [...events].reverse().find((e) => e.t < t - eps) ?? null;
}

// --- structure of the model, as the API extracted it from the URDF --------------------------------------------------

export type JointInfo = {
  name: string;
  type: string;
  parent: string;
  child: string;
  xyz: number[];
  rpy: number[];
  axis: number[] | null;
  limit: { lower: number | null; upper: number | null; effort: number | null; velocity: number | null } | null;
};
export type LinkInfo = { name: string; visuals: { mesh?: string; primitive?: string; rgba?: number[] }[] };
export type SensorInfo = { name: string; type: string; link: string | null; topic: string | null; frame: string | null; update_rate_hz: number | null };
export type ControllerInfo = { name: string; plugin: string; params: Record<string, string | string[]> };
export type Structure = { root: string; links: LinkInfo[]; joints: JointInfo[]; sensors: SensorInfo[]; controllers: ControllerInfo[] };

/** The joints a controller drives, read from its parameters (`left_joint`, `joint_name`, `joints`, ...). */
export function drivenJoints(c: ControllerInfo): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(c.params)) {
    if (!/joint/i.test(k)) continue;
    for (const x of Array.isArray(v) ? v : [v]) if (x) out.push(x);
  }
  return out;
}

/** Everything the model says about one link: its parent joint, the joints below it, sensors on it, controllers touching it. */
export function linkDetail(s: Structure, link: string) {
  const parent = s.joints.find((j) => j.child === link) ?? null;
  const children = s.joints.filter((j) => j.parent === link);
  const sensors = s.sensors.filter((x) => x.link === link);
  const drivers = parent ? s.controllers.filter((c) => drivenJoints(c).includes(parent.name)) : [];
  return { parent, children, sensors, drivers };
}

// --- a live or simulated observer ----------------------------------------------------------------------------------

type Json = Record<string, unknown>;
export type ObserverReads = { connectivity?: Json; joint_states?: Json; transforms?: Json };

/** The mode of an observed source. A replayed snapshot is "recorded" whatever kind of environment it sits in. */
export function observerMode(envKind: string, reads: ObserverReads, failed: boolean): { mode: Mode; reason: string } {
  if (failed || !reads.connectivity) return { mode: "disconnected", reason: "The observer did not answer." };
  if (reads.connectivity["recorded_not_live"] === true)
    return { mode: "recorded", reason: "A recorded snapshot replayed by the observer: values do not change." };
  const age = reads.connectivity["last_graph_poll_age_s"];
  if (typeof age === "number" && age > 5) return { mode: "disconnected", reason: `The observer has not seen the graph for ${age.toFixed(0)} s.` };
  const sources = (reads.joint_states?.["sources"] as unknown[] | undefined) ?? [];
  if (sources.length === 0) return { mode: "disconnected", reason: "No /joint_states is being published." };
  return envKind === "physical"
    ? { mode: "live", reason: "Read-only view of a physical robot's ROS 2 graph." }
    : { mode: "simulated", reason: "Read-only view of a simulated robot's ROS 2 graph." };
}

type Frame = { child: string; parent: string; translation: number[]; rotation: number[]; static: boolean };

export function yawOf(q: number[]): number {
  const [x = 0, y = 0, z = 0, w = 1] = q;
  return Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
}

/** The base pose from the observer's TF frames: the frame chain from `parent` down to `child`, composed in the plane. */
export function observerBasePose(transforms: Json | undefined, parent: string, child: string): Pose | null {
  const frames = ((transforms?.["frames"] as Frame[] | undefined) ?? []).filter((f) => Array.isArray(f.translation));
  const direct = frames.find((f) => f.parent === parent && f.child === child);
  if (!direct) return null;
  return { x: direct.translation[0] ?? 0, y: direct.translation[1] ?? 0, yaw: yawOf(direct.rotation) };
}

export function observerJoints(joint_states: Json | undefined): Record<string, number> {
  const out: Record<string, number> = {};
  for (const src of (joint_states?.["sources"] as { joints?: { name: string; position: number | null }[] }[] | undefined) ?? [])
    for (const j of src.joints ?? []) if (typeof j.position === "number") out[j.name] = j.position;
  return out;
}

/** How many reported joints exist in the model. Names are matched exactly; nothing is guessed. */
export function matchJoints(model: string[], reported: string[]): { matched: string[]; unmatched: string[] } {
  const have = new Set(model);
  return { matched: reported.filter((n) => have.has(n)), unmatched: reported.filter((n) => !have.has(n)) };
}

export const MODE_TEXT: Record<Mode, string> = {
  live: "Live",
  recorded: "Recorded",
  simulated: "Simulated",
  disconnected: "Disconnected",
};
