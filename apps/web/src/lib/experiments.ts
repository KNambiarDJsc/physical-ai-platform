/**
 * Experiment Studio logic with no React in it: how a scenario's JSON Schema becomes form fields, how a form becomes an
 * immutable spec (pap.experiment-spec/1), and how stored results are put into words. It computes no statistic: counts
 * of the engine's verdicts and the host's raw values are the most that is ever derived here.
 */
import type { Schemas } from "./api/client";

export type SimEnv = Schemas["SimEnvironmentOut"];
export type SimScenario = Schemas["SimScenarioOut"];
export type ExperimentOut = Schemas["ExperimentOut"];
export type ExperimentVersion = Schemas["ExperimentVersionOut"];
export type ExperimentRequest = Schemas["ExperimentRequestOut"];
export type ExperimentRequestDetail = Schemas["ExperimentRequestDetail"];
export type TrialResult = Schemas["TrialResultOut"];
export type ArmSummary = Schemas["ArmSummaryOut"];

// ------------------------------------------------------------------------------------------ schema → fields

export type Field = {
  key: string;
  label: string;
  help: string;
  kind: "number" | "integer" | "boolean" | "text" | "choice";
  required: boolean;
  min?: number;
  max?: number;
  choices?: string[];
  default?: string | boolean;
};

type Prop = { type?: string; description?: string; minimum?: number; maximum?: number; enum?: unknown[]; default?: unknown };
type ParamSchema = { properties?: Record<string, Prop>; required?: string[] };

const UNITS: Record<string, string> = { mps: "m/s", ms: "ms", m: "m", s: "s", deg: "°", rad: "rad", hz: "Hz", kg: "kg", g: "g" };

/** A parameter or measurement name without its unit suffix (`speed_mps` is "Speed"), and the unit if the name had one. */
export function splitUnit(key: string): { text: string; unit?: string } {
  const m = /^(.*[a-z])_(mps|ms|m|s|deg|rad|hz|kg|g)$/.exec(key);
  return m ? { text: humanize(m[1]!), unit: UNITS[m[2]!] } : { text: humanize(key) };
}

/** A measurement's name for people: no unit suffix (the unit is shown beside the value). */
export const measureLabel = (key: string): string => splitUnit(key).text;

/** Who a stored principal label stands for, without the identity provider's prefixes. */
export function person(label: string | null | undefined): string {
  if (!label) return "";
  const tail = label.includes("|") ? label.slice(label.lastIndexOf("|") + 1) : label.replace(/^(user|dev):/, "");
  return tail.replace(/^service:/, "service ");
}

export function humanize(key: string): string {
  const s = key.replace(/[_-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Form fields for a scenario's parameters. The seed is not a field: it is set from the repetitions. */
export function fieldsFor(schema: Record<string, unknown>): Field[] {
  const s = schema as ParamSchema;
  const required = new Set(s.required ?? []);
  return Object.entries(s.properties ?? {})
    .filter(([key]) => key !== "seed")
    .map(([key, p]): Field => {
      const kind = p.enum ? "choice" : p.type === "boolean" ? "boolean" : p.type === "integer" ? "integer" : p.type === "number" ? "number" : "text";
      return {
        key,
        label: ((u) => (u.unit ? `${u.text} (${u.unit})` : u.text))(splitUnit(key)),
        help: p.description ?? "",
        kind,
        required: required.has(key),
        min: p.minimum,
        max: p.maximum,
        choices: p.enum?.map(String),
        default: p.default === undefined ? undefined : typeof p.default === "boolean" ? p.default : String(p.default),
      };
    });
}

export const hasSeed = (schema: Record<string, unknown>): boolean => (schema as ParamSchema).properties?.seed?.type === "integer";

/** What is wrong with one typed value, in words, or null. The API checks the schema again; this is only quicker. */
export function fieldError(f: Field, raw: string | boolean | undefined): string | null {
  const blank = raw === undefined || raw === "";
  if (blank) return f.required ? "Required." : null;
  if (f.kind === "boolean" || f.kind === "text") return null;
  if (f.kind === "choice") return f.choices?.includes(String(raw)) ? null : "Pick one of the listed values.";
  const n = Number(raw);
  if (!Number.isFinite(n)) return "Enter a number.";
  if (f.kind === "integer" && !Number.isInteger(n)) return "Enter a whole number.";
  if (f.min !== undefined && n < f.min) return `At least ${f.min}.`;
  if (f.max !== undefined && n > f.max) return `At most ${f.max}.`;
  return null;
}

function typed(f: Field, raw: string | boolean): string | number | boolean {
  if (f.kind === "boolean") return raw === true || raw === "true";
  if (f.kind === "number" || f.kind === "integer") return Number(raw);
  return String(raw);
}

// ------------------------------------------------------------------------------------------------- the form

export type ArmForm = { key: string; title: string; role: "baseline" | "candidate"; values: Record<string, string | boolean> };
export type RuleOp = "le" | "lt" | "ge" | "gt" | "eq" | "between";
export type RuleForm = { measurement: string; op: RuleOp; value: string; max: string };
export type Form = {
  name: string;
  slug: string;
  description: string;
  environment: string;
  scenario: string; // id@version
  arms: ArmForm[];
  repetitions: string;
  varySeed: boolean;
  rules: RuleForm[];
  keep: string[]; // artifact names
  model: string; // project/model@version, or ""
  software: { name: string; revision: string }[];
  approverRole: "engineer" | "admin";
  distinctApprover: boolean;
  notes: string;
};

export const OP_WORDS: Record<RuleOp, string> = {
  le: "is at most",
  lt: "is below",
  ge: "is at least",
  gt: "is above",
  eq: "is exactly",
  between: "is between",
};

export const slugify = (s: string): string =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);

export const scenarioKey = (s: Pick<SimScenario, "id" | "version">): string => `${s.id}@${s.version}`;

/** Initial values for a new experiment: the schema's own defaults, a baseline and a candidate to compare. */
export function blankForm(env: SimEnv | undefined, sc: SimScenario | undefined): Form {
  const fields = sc ? fieldsFor(sc.parameters_schema) : [];
  const values = (): Record<string, string | boolean> =>
    Object.fromEntries(fields.flatMap((f) => (f.default !== undefined ? [[f.key, f.default]] : f.kind === "boolean" && f.required ? [[f.key, false]] : [])));
  const firstOut = sc?.outputs?.[0] as { name?: string } | undefined;
  return {
    name: "",
    slug: "",
    description: "",
    environment: env?.slug ?? "",
    scenario: sc ? scenarioKey(sc) : "",
    arms: [
      { key: "baseline", title: "Baseline", role: "baseline", values: values() },
      { key: "candidate", title: "Candidate", role: "candidate", values: values() },
    ],
    repetitions: "3",
    varySeed: !!sc && hasSeed(sc.parameters_schema),
    rules: [{ measurement: firstOut?.name ?? "", op: "le", value: "", max: "" }],
    keep: (sc?.artifacts ?? []).map((a) => (a as { name: string }).name),
    model: "",
    software: [{ name: "", revision: "" }],
    approverRole: "engineer",
    distinctApprover: true,
    notes: "",
  };
}

type Out = { name: string; unit?: string | null; description?: string };
const outputs = (sc: SimScenario): Out[] => sc.outputs as Out[];
type Art = { name: string; media_type?: string; description?: string };
const artifacts = (sc: SimScenario): Art[] => sc.artifacts as Art[];

export const unitOf = (sc: SimScenario | undefined, measurement: string): string => outputs(sc ?? ({ outputs: [] } as unknown as SimScenario)).find((o) => o.name === measurement)?.unit ?? "";
export const mcapArtifact = (sc: SimScenario): string | null => artifacts(sc).find((a) => a.media_type?.includes("mcap"))?.name ?? null;
const summaryArtifact = (sc: SimScenario): string | null => artifacts(sc).find((a) => a.media_type?.includes("json") && /summary/.test(a.name))?.name ?? null;

export function ruleSentence(sc: SimScenario | undefined, r: RuleForm): string {
  const unit = unitOf(sc, r.measurement);
  const u = unit ? ` ${unit}` : "";
  const label = measureLabel(r.measurement).toLowerCase();
  return r.op === "between" ? `${label} ${OP_WORDS.between} ${r.value}${u} and ${r.max}${u}` : `${label} ${OP_WORDS[r.op]} ${r.value}${u}`;
}

export type Problems = { fields: Record<string, string>; form: string[] };

/** Check a form and, if it is sound, build the spec the API stores. Every message says what to change. */
export function buildSpec(form: Form, env: SimEnv | undefined, sc: SimScenario | undefined): { spec?: Record<string, unknown>; problems: Problems } {
  const problems: Problems = { fields: {}, form: [] };
  const bad = (k: string, m: string) => (problems.fields[k] ??= m);
  if (!env || env.state !== "ready" || !env.simulator) problems.form.push("Choose a simulation environment that is ready.");
  if (!sc) problems.form.push("Choose a scenario.");
  if (!env || !sc || !env.simulator) return { problems };
  const fields = fieldsFor(sc.parameters_schema);
  if (!form.name.trim()) bad("name", "Give the experiment a name.");
  if (!form.slug) bad("slug", "The name needs at least one letter or digit.");
  const reps = Number(form.repetitions);
  if (!Number.isInteger(reps) || reps < 1 || reps > 50) bad("repetitions", "Enter a whole number from 1 to 50.");
  const keys = form.arms.map((a) => a.key);
  form.arms.forEach((a, i) => {
    if (!a.title.trim()) bad(`arm.${i}.title`, "Name this setup.");
    for (const f of fields) {
      const e = fieldError(f, a.values[f.key]);
      if (e) bad(`arm.${i}.${f.key}`, e);
    }
  });
  if (new Set(keys).size !== keys.length) problems.form.push("Two setups have the same name.");
  form.software.forEach((s, i) => {
    if (!s.name.trim()) bad(`software.${i}.name`, "Name the software.");
    if (!s.revision.trim()) bad(`software.${i}.revision`, "Give its revision (a commit, tag or version).");
  });
  form.rules.forEach((r, i) => {
    if (!r.measurement) bad(`rule.${i}.measurement`, "Choose a measurement.");
    if (r.value.trim() === "" || !Number.isFinite(Number(r.value))) bad(`rule.${i}.value`, "Enter a number.");
    if (r.op === "between" && (r.max.trim() === "" || !Number.isFinite(Number(r.max)))) bad(`rule.${i}.max`, "Enter a number.");
    if (r.op === "between" && Number(r.max) < Number(r.value)) bad(`rule.${i}.max`, "The upper bound is below the lower.");
  });
  if (form.rules.length === 0) problems.form.push("Add at least one rule that decides pass or fail.");
  if (Object.keys(problems.fields).length || problems.form.length) return { problems };

  // Parameters identical in every setup are the experiment's shared conditions; only what differs belongs to a setup.
  const per = form.arms.map((a) => Object.fromEntries(fields.filter((f) => a.values[f.key] !== undefined && a.values[f.key] !== "").map((f) => [f.key, typed(f, a.values[f.key] as string | boolean)])));
  const shared: Record<string, unknown> = {};
  const first = per[0] ?? {};
  if (per.length > 1) for (const f of fields) if (per.every((p) => f.key in p && p[f.key] === first[f.key])) shared[f.key] = first[f.key];
  const keep = form.keep.filter((n) => artifacts(sc).some((a) => a.name === n));
  const mcap = mcapArtifact(sc);
  const recording = form.model && mcap && keep.includes(mcap) ? mcap : null;
  const summary = recording && summaryArtifact(sc) && keep.includes(summaryArtifact(sc)!) ? summaryArtifact(sc) : null;
  const [project, rest] = form.model.split("/");
  const [model, version] = (rest ?? "").split("@");
  const trials = form.arms.length * reps;
  const spec: Record<string, unknown> = {
    environment: env.slug,
    simulator: env.simulator,
    scenario: { id: sc.id, version: sc.version, definition_sha256: sc.definition_sha256 },
    ...(form.model ? { model: { project, model, version: Number(version) } } : {}),
    software: form.software.map((s) => ({ name: s.name.trim(), revision: s.revision.trim() })),
    initial_conditions: shared,
    seeds: form.varySeed && hasSeed(sc.parameters_schema) ? Array.from({ length: reps }, (_, i) => i + 1) : [],
    repetitions: reps,
    arms: form.arms.map((a, i) => ({
      key: a.key,
      title: a.title.trim(),
      role: a.role,
      parameters: Object.fromEntries(Object.entries(per[i] ?? {}).filter(([k]) => !(k in shared))),
    })),
    limits: { max_trials: trials, max_wall_time_s: Math.max(1, Math.ceil(trials * sc.max_duration_s)) },
    observations: {
      measurements: outputs(sc).map((o) => o.name),
      artifacts: keep,
      ...(recording ? { recording } : {}),
      ...(summary ? { summary } : {}),
    },
    contract: {
      name: `${form.slug}-rule`.slice(0, 64).replace(/^[^a-z]+/, "r"),
      version: "1",
      conditions: form.rules.map((r) => ({
        name: ruleSentence(sc, r).replace(/^./, (c) => c.toUpperCase()),
        measurement: r.measurement,
        op: r.op,
        ...(r.op === "between" ? { min: Number(r.value), max: Number(r.max) } : { value: Number(r.value) }),
      })),
    },
    approval: { role: form.approverRole, distinct_approver: form.distinctApprover },
  };
  return { spec, problems };
}

type SpecArm = { key: string; title?: string; role: "baseline" | "candidate"; parameters: Record<string, unknown> };
type SpecCond = { measurement: string; op: RuleOp; value?: number; min?: number; max?: number };

/** A stored spec back into a form, to make a changed version of it. */
export function formFromSpec(spec: Record<string, unknown>, exp: { name: string; slug: string; description: string }): Form {
  const s = spec as {
    environment: string;
    arms: SpecArm[];
    initial_conditions: Record<string, unknown>;
    repetitions: number;
    seeds: number[];
    software: { name: string; revision: string }[];
    contract: { conditions: SpecCond[] };
    observations: { artifacts: string[] };
    model?: { project: string; model: string; version: number };
    approval: { role: "engineer" | "admin"; distinct_approver: boolean };
    scenario: { id: string; version: string };
  };
  const str = (v: unknown): string | boolean => (typeof v === "boolean" ? v : String(v));
  return {
    name: exp.name,
    slug: exp.slug,
    description: exp.description,
    environment: s.environment,
    scenario: `${s.scenario.id}@${s.scenario.version}`,
    arms: s.arms.map((a) => ({
      key: a.key,
      title: a.title || a.key,
      role: a.role,
      values: Object.fromEntries(Object.entries({ ...s.initial_conditions, ...a.parameters }).map(([k, v]) => [k, str(v)])),
    })),
    repetitions: String(s.repetitions),
    varySeed: s.seeds.length > 0,
    rules: s.contract.conditions.map((c) => ({ measurement: c.measurement, op: c.op, value: String(c.op === "between" ? c.min : c.value), max: c.op === "between" ? String(c.max) : "" })),
    keep: s.observations.artifacts,
    model: s.model ? `${s.model.project}/${s.model.model}@${s.model.version}` : "",
    software: s.software,
    approverRole: s.approval.role,
    distinctApprover: s.approval.distinct_approver,
    notes: "",
  };
}

// ---------------------------------------------------------------------------------------------------- results

export const TRIAL_FINAL = ["succeeded", "failed", "outcome_unknown", "cancelled"];
export const isFinal = (t: TrialResult): boolean => TRIAL_FINAL.includes(t.state);
export const capturePending = (t: TrialResult): boolean => t.capture_state === "pending";

/** True while anything on the request is still moving, so the page keeps refreshing. */
export const inFlight = (d: ExperimentRequestDetail | undefined): boolean =>
  !!d && d.state === "approved" && d.trial_results.some((t) => !isFinal(t) || (t.state === "succeeded" && capturePending(t)));

export function trialWords(t: TrialResult): string {
  if (t.state === "queued") return "Waiting for the worker";
  if (t.state === "running") return "Running on the host";
  if (t.state === "succeeded") return "Finished";
  if (t.state === "outcome_unknown") return "Outcome unknown";
  if (t.state === "cancelled") return "Cancelled";
  return "Failed";
}

/** Why a trial failed, in the user's terms, and what they can do about it. */
export function failureHelp(t: TrialResult): { what: string; next: string } | null {
  if (t.state === "failed" || t.state === "outcome_unknown") {
    const e = t.error as { code?: string; message?: string } | null;
    const what = e?.message ?? "The trial did not finish.";
    const next =
      t.state === "outcome_unknown"
        ? "The host may still be running it. Check the host, then request a new run."
        : e?.code === "environment_unavailable" || e?.code === "device.unreachable"
          ? "The host could not be reached. Make sure it is running, then request a new run."
          : "Nothing was measured for this trial. Request a new run when the cause is fixed.";
    return { what, next };
  }
  if (t.capture_state === "failed") return { what: t.capture_error ?? "The files could not be captured.", next: "The measurements and verdict are kept; the files that failed their checks were not stored." };
  return null;
}

export type VerdictCounts = { satisfied: number; violated: number; other: number; pending: number };
export function verdictCounts(a: ArmSummary, total: number): VerdictCounts {
  const v = a.verdicts as Record<string, number>;
  const satisfied = v.SATISFIED ?? 0;
  const violated = v.VIOLATED ?? 0;
  const judged = Object.values(v).reduce((x, y) => x + y, 0);
  return { satisfied, violated, other: judged - satisfied - violated, pending: Math.max(0, total - judged) };
}

export function armSentence(c: VerdictCounts, n: number): string {
  const parts: string[] = [];
  if (c.satisfied) parts.push(`${c.satisfied} of ${n} met the rule`);
  if (c.violated) parts.push(`${c.violated} of ${n} broke it`);
  if (c.other) parts.push(`${c.other} could not be judged`);
  if (c.pending) parts.push(`${c.pending} not finished`);
  return parts.length ? parts.join(", ") : "No trial yet";
}

export function requestStatus(r: { state: string; trials: number; trials_done: number }): { tone: "neutral" | "accent" | "ok" | "bad" | "warn"; text: string } {
  if (r.state === "awaiting_approval") return { tone: "warn", text: "Waiting for approval" };
  if (r.state === "rejected") return { tone: "bad", text: "Rejected" };
  if (r.trials_done < r.trials) return { tone: "accent", text: `Running · ${r.trials_done} of ${r.trials} done` };
  return { tone: "ok", text: `Finished · ${r.trials} trial${r.trials === 1 ? "" : "s"}` };
}

export const shortSum = (d: string): string => d.replace(/^sha256:/, "").slice(0, 10);

/** A measured value with its unit, as the host reported it (never rounded beyond what the host wrote). */
export function measured(v: unknown, unit: string): string {
  if (v === null || v === undefined) return "—";
  return typeof v === "number" ? `${Number.isInteger(v) ? v : Number(v.toPrecision(6))}${unit ? ` ${unit}` : ""}` : String(v);
}
