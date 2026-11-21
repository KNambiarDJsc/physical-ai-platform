import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { num, ObsState, ValueView } from "./Observation";

// A snapshot RECORDED from a real ROS 2 graph (runtimes/ros-observer/tests_ros/test_live_graph.py).
const snap = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../../../runtimes/ros-observer/tests/fixtures/openamr-upperbody-mock.snapshot.json"), "utf-8"),
).things as Record<string, Record<string, unknown>>;

const G = snap["ros-graph"]!;
const R = snap["ros-robot"]!;

describe("ValueView on observations recorded from a real ROS graph", () => {
  it("shows every topic with its state as text, not colour alone", () => {
    const topics = G.topics as { name: string; state: string }[];
    render(<ValueView name="topics" value={topics} />);
    const table = screen.getByRole("table", { name: "topics" });
    expect(within(table).getAllByRole("row")).toHaveLength(topics.length + 1);
    for (const state of new Set(topics.map((t) => t.state))) {
      expect(within(table).getAllByText(state.replace(/_/g, " ")).length).toBeGreaterThan(0);
    }
  });

  it("formats ages and rates with units and leaves an absent age as an em dash", () => {
    expect(num(2.5, "age_s")).toBe("2.500 s");
    expect(num(12.3456, "age_s")).toBe("12.3 s");
    expect(num(100.98, "rate_hz")).toBe("101.0 Hz");
    render(<ValueView name="x" value={[{ name: "/never", state: "never", age_s: null }]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("lists every joint of the recorded /joint_states with its position", () => {
    const joints = (R.joint_states as { sources: { joints: { name: string }[] }[] }).sources[0]!.joints;
    render(<ValueView name="joint_states" value={R.joint_states} />);
    for (const j of joints) expect(screen.getByText(j.name)).toBeInTheDocument();
    expect(joints.length).toBe(17);
  });

  it("marks a REQUIRED topic that is missing as a problem and an optional one only as missing", () => {
    const rows = [
      { name: "/need", required: true, state: "missing", age_s: null },
      { name: "/opt", required: false, state: "missing", age_s: null },
    ];
    const { container } = render(<ValueView name="expected_topics" value={rows} />);
    const [need, opt] = Array.from(container.querySelectorAll("tbody tr"));
    expect(need!.querySelector("span.bg-bad-soft")).not.toBeNull();
    expect(opt!.querySelector("span.bg-bad-soft")).toBeNull();
    expect(opt!.querySelector("span.bg-unknown-soft")).not.toBeNull();
  });

  it("renders records as definition lists and nested record arrays as sub-tables", () => {
    render(<ValueView name="controllers" value={R.controllers} />);
    expect(screen.getByRole("table", { name: "controllers" })).toBeInTheDocument();
    expect(screen.getAllByText("active").length).toBeGreaterThanOrEqual(6);
  });

  it("shows an empty value honestly", () => {
    render(<ValueView name="p" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    render(<ObsState value="not_sampled" />);
    expect(screen.getByText("not sampled")).toBeInTheDocument();
  });
});
