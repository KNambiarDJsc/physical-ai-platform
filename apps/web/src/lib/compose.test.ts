import { describe, expect, it } from "vitest";
import type { Device } from "./api/client";
import { buildDefinition, inputFields, openOutput, outputFields, type ComposeForm } from "./compose";

// The shape of the virtual laboratory's devices as discovery records them (runtimes/virtual-lab).
const devices = [
  {
    key: "pump",
    capabilities: [
      {
        kind: "action", name: "dispense", idempotency_key: "request_id",
        input_schema: { type: "object", required: ["volume_ul"], properties: { volume_ul: { type: "number", minimum: 0, maximum: 1000 }, request_id: { type: "string" } } },
        output_schema: { type: "object", properties: { dispensed_ul: { type: "number" } } },
      },
    ],
  },
  {
    key: "balance",
    capabilities: [
      { kind: "action", name: "tare", idempotency_key: null, input_schema: { type: "object", properties: {} }, output_schema: null },
      { kind: "action", name: "weigh", idempotency_key: null, input_schema: { type: "object", properties: {} },
        output_schema: { type: "object", properties: { mass_g: { type: "number" }, stable: { type: "boolean" } } } },
      { kind: "property", name: "mass_g", idempotency_key: null, input_schema: null, output_schema: null },
    ],
  },
] as unknown as Device[];

const form = (): ComposeForm => ({
  name: "Two dispenses then weigh",
  environment: "virtual-lab",
  steps: [
    { device: "balance", action: "tare", title: "", values: {} },
    { device: "pump", action: "dispense", title: "", values: { volume_ul: "50" } },
    { device: "pump", action: "dispense", title: "", values: { volume_ul: "30" } },
    { device: "balance", action: "weigh", title: "", values: {} },
  ],
  verify: true,
  claimStep: 2,
  evidence: [{ step: 3, field: "mass_g", signal: "vessel.net_mass", unit: "g" }],
  conditions: [{ evidence: 0, op: "between", value: "0.0783", max: "0.0815" }],
});

describe("composing a multi-instrument workflow", () => {
  it("reads each action's inputs and evidence-capable outputs from its own schema, without the idempotency key", () => {
    expect(inputFields(devices[0]!.capabilities[0]).map((f) => f.key)).toEqual(["volume_ul"]);
    expect(outputFields(devices[1]!.capabilities[1])).toEqual(["mass_g", "stable"]);
    // an action that returns dict[str, float] names no field: the person types it
    const open = { kind: "action", name: "weigh", output_schema: { type: "object", additionalProperties: { type: "number" } } };
    expect(outputFields(open as never)).toEqual([]);
    expect(openOutput(open as never)).toBe(true);
    expect(openOutput(devices[1]!.capabilities[1])).toBe(false);
  });

  it("builds a pap.workflow/1 definition across instruments with the engine's verification contract", () => {
    const { definition, problems } = buildDefinition(form(), devices);
    expect(problems).toEqual({ fields: {}, form: [] });
    const d = definition as { steps: { id: string; device: string; action: string; input: unknown }[]; verification: Record<string, unknown> };
    expect(d.steps.map((s) => [s.id, s.device, s.action, s.input])).toEqual([
      ["s1", "balance", "tare", {}],
      ["s2", "pump", "dispense", { volume_ul: 50 }],
      ["s3", "pump", "dispense", { volume_ul: 30 }],
      ["s4", "balance", "weigh", {}],
    ]);
    expect(d.verification).toMatchObject({
      claim_step: "s3",
      evidence: [{ name: "mass_g", step: "s4", output_field: "mass_g", signal: "vessel.net_mass", unit: "g", kind: "independent_sensor" }],
      conditions: [{ evidence: "mass_g", op: "between", min: { value: 0.0783, unit: "g" }, max: { value: 0.0815, unit: "g" } }],
    });
  });

  it("refuses what the engine could not check, in words, and builds nothing", () => {
    const f = form();
    f.steps[1]!.values.volume_ul = "5000";
    f.evidence[0]!.step = 2; // the claim's own step is not independent evidence
    f.conditions[0]!.max = "";
    const r = buildDefinition(f, devices);
    expect(r.definition).toBeUndefined();
    expect(r.problems.fields).toMatchObject({
      "step.1.volume_ul": "At most 1000.",
      "evidence.0.step": "Evidence must come from a different step than the claim.",
      "condition.0.max": "Enter a number.",
    });
  });

  it("can be a plain sequence without verification", () => {
    const f = { ...form(), verify: false };
    expect(buildDefinition(f, devices).definition).not.toHaveProperty("verification");
  });
});
