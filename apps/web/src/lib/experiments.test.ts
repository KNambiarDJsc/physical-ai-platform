import { describe, expect, it } from "vitest";
import {
  armSentence,
  blankForm,
  buildSpec,
  fieldError,
  fieldsFor,
  formFromSpec,
  humanize,
  inFlight,
  measureLabel,
  measured,
  person,
  requestStatus,
  ruleSentence,
  splitUnit,
  verdictCounts,
  type ArmSummary,
  type ExperimentRequestDetail,
  type SimEnv,
  type SimScenario,
} from "./experiments";

// The shape of the self-test host's drive scenario as the host lists it (see runtimes/sim-host/catalogs/selftest.json).
const scenario = {
  id: "selftest-drive",
  version: "1",
  title: "Self-test: base stop on command loss",
  description: "",
  definition_sha256: "sha256:" + "a".repeat(64),
  max_duration_s: 30,
  parameters_schema: {
    type: "object",
    required: ["stop_on_command_loss"],
    properties: {
      stop_on_command_loss: { type: "boolean", description: "Stop the base when commands stop arriving." },
      speed_mps: { type: "number", minimum: 0.05, maximum: 1, default: 0.3, description: "Commanded forward speed, m/s." },
      drive_s: { type: "number", minimum: 0.5, maximum: 10, default: 2 },
      seed: { type: "integer", minimum: 0, maximum: 2147483647 },
    },
  },
  outputs: [
    { name: "travel_after_kill_m", unit: "m" },
    { name: "driven_before_kill_m", unit: "m" },
  ],
  artifacts: [{ name: "recording", media_type: "application/x-mcap" }],
} as unknown as SimScenario;

const env = {
  slug: "selftest-sim",
  name: "Self-test",
  state: "ready",
  simulator: { kind: "selftest", name: "Host self-test", version: null },
  scenarios: [scenario],
} as unknown as SimEnv;

type BuiltSpec = {
  initial_conditions: Record<string, unknown>;
  arms: { key: string; parameters: Record<string, unknown> }[];
  scenario: unknown;
  seeds: number[];
  limits: unknown;
  contract: { conditions: unknown[] };
  observations: { measurements: string[]; recording?: string };
  approval: unknown;
  model?: unknown;
};

function filled() {
  const f = blankForm(env, scenario);
  f.name = "Stop on command loss";
  f.slug = "stop-on-command-loss";
  f.arms[0]!.values.stop_on_command_loss = false;
  f.arms[1]!.values.stop_on_command_loss = true;
  f.rules = [{ measurement: "travel_after_kill_m", op: "le", value: "0.15", max: "" }];
  f.software = [{ name: "controller", revision: "505d17a" }];
  return f;
}

describe("form fields from a scenario's schema", () => {
  it("makes a field per parameter, never for the seed, with the schema's limits and defaults", () => {
    const fields = fieldsFor(scenario.parameters_schema);
    expect(fields.map((f) => f.key)).toEqual(["stop_on_command_loss", "speed_mps", "drive_s"]);
    const speed = fields.find((f) => f.key === "speed_mps")!;
    expect(speed).toMatchObject({ kind: "number", min: 0.05, max: 1, default: "0.3", required: false, label: "Speed (m/s)" });
    expect(fields[0]!).toMatchObject({ kind: "boolean", required: true });
  });

  it("refuses values outside the schema, in words, before anything is submitted", () => {
    const speed = fieldsFor(scenario.parameters_schema)[1]!;
    expect(fieldError(speed, "5")).toBe("At most 1.");
    expect(fieldError(speed, "0.01")).toBe("At least 0.05.");
    expect(fieldError(speed, "fast")).toBe("Enter a number.");
    expect(fieldError(speed, "0.5")).toBeNull();
    expect(fieldError(speed, "")).toBeNull(); // optional: the host's default applies
    expect(fieldError(fieldsFor(scenario.parameters_schema)[0]!, undefined)).toBe("Required.");
    expect(humanize("stop_on_command_loss")).toBe("Stop on command loss");
  });
});

describe("building the immutable spec", () => {
  it("puts what is the same in every setup into shared conditions and only what differs into a setup", () => {
    const { spec, problems } = buildSpec(filled(), env, scenario);
    expect(problems).toEqual({ fields: {}, form: [] });
    const s = spec as unknown as BuiltSpec;
    expect(s.initial_conditions).toEqual({ speed_mps: 0.3, drive_s: 2 });
    expect(s.arms.map((a) => [a.key, a.parameters])).toEqual([
      ["baseline", { stop_on_command_loss: false }],
      ["candidate", { stop_on_command_loss: true }],
    ]);
    expect(s.scenario).toEqual({ id: "selftest-drive", version: "1", definition_sha256: scenario.definition_sha256 });
    expect(s.seeds).toEqual([1, 2, 3]); // one seed per repetition, so trials differ and can be repeated
    expect(s.limits).toEqual({ max_trials: 6, max_wall_time_s: 180 }); // 2 setups x 3 repetitions x the scenario's 30 s
    expect(s.contract.conditions).toEqual([
      { name: "Travel after kill is at most 0.15 m", measurement: "travel_after_kill_m", op: "le", value: 0.15 },
    ]);
    expect(s.observations.measurements).toEqual(["travel_after_kill_m", "driven_before_kill_m"]);
    expect(s.approval).toEqual({ role: "engineer", distinct_approver: true });
    expect("recording" in s.observations).toBe(false); // no robot model chosen, so nothing is registered in the twin
  });

  it("registers the recording in the twin only when a robot model is chosen", () => {
    const f = filled();
    f.model = "robots/openamr@1";
    const s = buildSpec(f, env, scenario).spec as unknown as BuiltSpec;
    expect(s.model).toEqual({ project: "robots", model: "openamr", version: 1 });
    expect(s.observations.recording).toBe("recording");
  });

  it("says what to change for each problem and builds nothing", () => {
    const f = filled();
    f.arms[1]!.values.speed_mps = "9";
    f.software = [{ name: "", revision: "" }];
    f.rules = [{ measurement: "travel_after_kill_m", op: "between", value: "2", max: "1" }];
    f.repetitions = "0";
    const r = buildSpec(f, env, scenario);
    expect(r.spec).toBeUndefined();
    expect(r.problems.fields).toMatchObject({
      "arm.1.speed_mps": "At most 1.",
      "software.0.name": "Name the software.",
      "software.0.revision": "Give its revision (a commit, tag or version).",
      "rule.0.max": "The upper bound is below the lower.",
      repetitions: "Enter a whole number from 1 to 50.",
    });
  });

  it("refuses an environment that is not ready", () => {
    const down = { ...env, state: "unreachable" } as SimEnv;
    expect(buildSpec(filled(), down, scenario).problems.form).toEqual(["Choose a simulation environment that is ready."]);
  });

  it("round-trips a stored spec into a form for a changed version", () => {
    const spec = buildSpec(filled(), env, scenario).spec!;
    const back = formFromSpec(spec, { name: "Stop on command loss", slug: "stop-on-command-loss", description: "" });
    expect(back.arms[1]!.values).toMatchObject({ stop_on_command_loss: true, speed_mps: "0.3" });
    expect(back.repetitions).toBe("3");
    expect(back.rules).toEqual([{ measurement: "travel_after_kill_m", op: "le", value: "0.15", max: "" }]);
    expect(buildSpec(back, env, scenario).spec).toEqual(spec); // an unchanged form is the same spec, so the same checksum
  });

  it("names things for people: units come off the identifier and principals lose their prefixes", () => {
    expect(splitUnit("command_timeout_s")).toEqual({ text: "Command timeout", unit: "s" });
    expect(splitUnit("speed_mps")).toEqual({ text: "Speed", unit: "m/s" });
    expect(splitUnit("stop_on_command_loss")).toEqual({ text: "Stop on command loss" });
    expect(measureLabel("travel_after_kill_m")).toBe("Travel after kill");
    expect(person("user:dev|ada-1")).toBe("ada-1");
    expect(person("service:ci")).toBe("service ci");
    expect(person("user:https://id.example|abc")).toBe("abc");
    expect(person(null)).toBe("");
  });

  it("writes a rule as a sentence with the measurement's own unit", () => {
    expect(ruleSentence(scenario, { measurement: "travel_after_kill_m", op: "between", value: "0", max: "0.15" })).toBe(
      "travel after kill is between 0 m and 0.15 m",
    );
  });
});

describe("results in words", () => {
  const arm = (verdicts: Record<string, number>): ArmSummary =>
    ({ arm: "a", title: "", role: "baseline", parameters: {}, trials: 3, states: {}, verdicts, values: {} }) as ArmSummary;

  it("counts the engine's verdicts and says what is still pending, without computing a statistic", () => {
    const c = verdictCounts(arm({ SATISFIED: 1, VIOLATED: 1 }), 3);
    expect(c).toEqual({ satisfied: 1, violated: 1, other: 0, pending: 1 });
    expect(armSentence(c, 3)).toBe("1 of 3 met the rule, 1 of 3 broke it, 1 not finished");
    expect(armSentence({ satisfied: 0, violated: 0, other: 0, pending: 0 }, 0)).toBe("No trial yet");
    expect(verdictCounts(arm({ UNKNOWN: 2 }), 2).other).toBe(2);
  });

  it("states a request's progress", () => {
    expect(requestStatus({ state: "awaiting_approval", trials: 0, trials_done: 0 }).text).toBe("Waiting for approval");
    expect(requestStatus({ state: "approved", trials: 4, trials_done: 1 }).text).toBe("Running · 1 of 4 done");
    expect(requestStatus({ state: "approved", trials: 4, trials_done: 4 }).text).toBe("Finished · 4 trials");
  });

  it("keeps refreshing only while something is moving", () => {
    const d = (state: string, cap: string) =>
      ({ state: "approved", trial_results: [{ state, capture_state: cap }] }) as unknown as ExperimentRequestDetail;
    expect(inFlight(d("running", "pending"))).toBe(true);
    expect(inFlight(d("succeeded", "pending"))).toBe(true); // finished, files not yet captured
    expect(inFlight(d("succeeded", "stored"))).toBe(false);
    expect(inFlight(d("failed", "none"))).toBe(false);
  });

  it("shows a measurement as the host wrote it, with its unit, and a dash for nothing", () => {
    expect(measured(0.132, "m")).toBe("0.132 m");
    expect(measured(3, "")).toBe("3");
    expect(measured(null, "m")).toBe("—");
  });
});
