/**
 * Composing a multi-instrument workflow from what discovery found: ordered device actions (each action's inputs from
 * its own JSON Schema) and, optionally, a verification contract the engine checks (which step is the claim, which step
 * outputs are independent evidence, the conditions). Builds a pap.workflow/1 definition; the API checks it again
 * against the environment's devices. Nothing here runs anything.
 */
import type { Capability, Device } from "./api/client";
import { fieldError, fieldsFor, humanize, slugify, type Field, type RuleOp, OP_WORDS } from "./experiments";

export type StepForm = { device: string; action: string; title: string; values: Record<string, string | boolean> };
export type EvidenceForm = { step: number; field: string; signal: string; unit: string };
export type ConditionForm = { evidence: number; op: RuleOp; value: string; max: string };
export type ComposeForm = {
  name: string;
  environment: string;
  steps: StepForm[];
  verify: boolean;
  claimStep: number;
  evidence: EvidenceForm[];
  conditions: ConditionForm[];
};

export const actionsOf = (d: Device | undefined): Capability[] => (d?.capabilities ?? []).filter((c) => c.kind === "action");
export const capability = (devices: Device[], s: StepForm): Capability | undefined => actionsOf(devices.find((d) => d.key === s.device)).find((c) => c.name === s.action);

/** The fields of an action's input, without the idempotency key (the worker sets it). */
export function inputFields(c: Capability | undefined): Field[] {
  if (!c?.input_schema) return [];
  return fieldsFor(c.input_schema as Record<string, unknown>).filter((f) => f.key !== c.idempotency_key);
}

/** True when an action returns an object without naming its fields (e.g. dict[str, float]): the person names it. */
export function openOutput(c: Capability | undefined): boolean {
  const o = (c?.output_schema ?? null) as { type?: string; properties?: Record<string, unknown> } | null;
  return !!o && o.type === "object" && Object.keys(o.properties ?? {}).length === 0;
}

/** Numeric fields an action returns: what can be evidence. */
export function outputFields(c: Capability | undefined): string[] {
  const props = ((c?.output_schema ?? {}) as { properties?: Record<string, { type?: string }> }).properties ?? {};
  return Object.entries(props)
    .filter(([, p]) => p.type === "number" || p.type === "integer" || p.type === "boolean")
    .map(([k]) => k);
}

const KEY = /^[a-z][a-z0-9_-]{0,63}$/;
const evidenceName = (e: EvidenceForm, i: number) => {
  const n = slugify(e.field).replace(/-/g, "_");
  return KEY.test(n) ? `${n}${i ? `_${i + 1}` : ""}` : `evidence_${i + 1}`;
};

export function conditionSentence(form: ComposeForm, c: ConditionForm): string {
  const e = form.evidence[c.evidence];
  const label = e ? humanize(e.field).toLowerCase() : "evidence";
  const u = e?.unit ? ` ${e.unit}` : "";
  return c.op === "between" ? `${label} is between ${c.value}${u} and ${c.max}${u}` : `${label} ${OP_WORDS[c.op]} ${c.value}${u}`;
}

export type ComposeProblems = { fields: Record<string, string>; form: string[] };

export function buildDefinition(form: ComposeForm, devices: Device[]): { definition?: Record<string, unknown>; problems: ComposeProblems } {
  const problems: ComposeProblems = { fields: {}, form: [] };
  const bad = (k: string, m: string) => (problems.fields[k] ??= m);
  if (!form.name.trim() || !slugify(form.name)) bad("name", "Give the workflow a name.");
  if (!form.environment) problems.form.push("Choose an environment.");
  if (form.steps.length === 0) problems.form.push("Add at least one step.");
  form.steps.forEach((s, i) => {
    const c = capability(devices, s);
    if (!s.device) bad(`step.${i}.device`, "Choose an instrument.");
    else if (!c) bad(`step.${i}.action`, "Choose an action.");
    for (const f of inputFields(c)) {
      const e = fieldError(f, s.values[f.key]);
      if (e) bad(`step.${i}.${f.key}`, e);
    }
  });
  if (form.verify) {
    if (!form.steps[form.claimStep]) bad("claim", "Choose the step whose report is the claim.");
    if (form.evidence.length === 0) problems.form.push("Add at least one piece of evidence, or turn verification off.");
    form.evidence.forEach((e, i) => {
      if (!form.steps[e.step]) bad(`evidence.${i}.step`, "Choose the step that measures it.");
      if (!e.field) bad(`evidence.${i}.field`, "Choose what it measured.");
      if (!e.signal.trim()) bad(`evidence.${i}.signal`, "Name the signal, e.g. vessel.net_mass.");
      if (e.step === form.claimStep) bad(`evidence.${i}.step`, "Evidence must come from a different step than the claim.");
    });
    if (form.conditions.length === 0) problems.form.push("Add at least one condition.");
    form.conditions.forEach((c, i) => {
      if (!form.evidence[c.evidence]) bad(`condition.${i}.evidence`, "Choose the evidence it checks.");
      if (c.value.trim() === "" || !Number.isFinite(Number(c.value))) bad(`condition.${i}.value`, "Enter a number.");
      if (c.op === "between" && (c.max.trim() === "" || !Number.isFinite(Number(c.max)))) bad(`condition.${i}.max`, "Enter a number.");
    });
  }
  if (Object.keys(problems.fields).length || problems.form.length) return { problems };

  const ids = form.steps.map((_, i) => `s${i + 1}`);
  const steps = form.steps.map((s, i) => {
    const c = capability(devices, s)!;
    const input = Object.fromEntries(
      inputFields(c)
        .filter((f) => s.values[f.key] !== undefined && s.values[f.key] !== "")
        .map((f) => [f.key, f.kind === "boolean" ? s.values[f.key] === true || s.values[f.key] === "true" : f.kind === "number" || f.kind === "integer" ? Number(s.values[f.key]) : String(s.values[f.key])]),
    );
    return { id: ids[i], device: s.device, action: s.action, input, title: s.title.trim() || `${humanize(s.action)} (${s.device})` };
  });
  const names = form.evidence.map(evidenceName);
  const operand = (x: string, unit: string) => (unit ? { value: Number(x), unit } : Number(x));
  const definition: Record<string, unknown> = { schema: "pap.workflow/1", steps };
  if (form.verify) {
    definition.verification = {
      contract: `${slugify(form.name)}-contract`.slice(0, 120),
      version: "1",
      claim_step: ids[form.claimStep],
      evidence: form.evidence.map((e, i) => ({
        name: names[i], step: ids[e.step], output_field: e.field, signal: e.signal.trim(),
        ...(e.unit ? { unit: e.unit } : {}), kind: "independent_sensor",
      })),
      conditions: form.conditions.map((c) => {
        const unit = form.evidence[c.evidence]!.unit;
        const base = { name: conditionSentence(form, c).replace(/^./, (x) => x.toUpperCase()), evidence: names[c.evidence], op: c.op };
        return c.op === "between" ? { ...base, min: operand(c.value, unit), max: operand(c.max, unit) } : { ...base, value: operand(c.value, unit) };
      }),
    };
  }
  return { definition, problems };
}
