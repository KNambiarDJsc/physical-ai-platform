"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, orgPath } from "@/lib/api/client";
import {
  OP_WORDS,
  blankForm,
  buildSpec,
  fieldsFor,
  formFromSpec,
  hasSeed,
  humanize,
  mcapArtifact,
  measureLabel,
  ruleSentence,
  scenarioKey,
  slugify,
  unitOf,
  type ExperimentOut,
  type ExperimentVersion,
  type Field,
  type Form,
  type RuleOp,
  type SimEnv,
  type SimScenario,
} from "@/lib/experiments";
import { Notice, PageHeader } from "../AppShell";
import { Badge } from "../ui";
import { Crumbs, ErrorNotice, useExperiments, useModels, useSimEnvs } from "./common";

type Existing = { exp: ExperimentOut; version: ExperimentVersion };

const ENV_STATE: Record<SimEnv["state"], { tone: "ok" | "bad" | "warn"; text: string; fix: string }> = {
  ready: { tone: "ok", text: "Ready", fix: "" },
  unreachable: { tone: "bad", text: "Not answering", fix: "The host did not answer. Make sure it is running, then check again." },
  no_host: { tone: "warn", text: "Not discovered", fix: "Run discovery on this environment in the Hardware Hub." },
  unavailable: { tone: "bad", text: "Removed by the operator", fix: "The operator no longer offers this environment." },
  invalid: { tone: "bad", text: "Not usable", fix: "The host's listing could not be used." },
};

function Section({ n, title, children, help }: { n: number; title: string; help?: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`sec-${n}`} className="rounded-md border border-line bg-panel">
      <div className="border-b border-line px-4 py-2.5">
        <h2 id={`sec-${n}`} className="text-[13px] font-medium">
          <span className="num mr-2 text-faint">{n}</span>
          {title}
        </h2>
        {help && <p className="mt-0.5 pl-5 text-[12px] text-muted">{help}</p>}
      </div>
      <div className="space-y-3 p-4">{children}</div>
    </section>
  );
}

const errId = (k: string) => `err-${k.replace(/[^a-z0-9]/gi, "-")}`;

function FieldError({ k, errors, show }: { k: string; errors: Record<string, string>; show: boolean }) {
  return show && errors[k] ? (
    <p id={errId(k)} className="mt-0.5 text-[12px] text-bad">
      {errors[k]}
    </p>
  ) : null;
}

function armKey(title: string, taken: string[]): string {
  let base = slugify(title).replace(/^[^a-z]+/, "") || "setup";
  base = base.slice(0, 40);
  let k = base;
  for (let i = 2; taken.includes(k); i++) k = `${base}-${i}`;
  return k;
}

export function Configure({ org, role, existing, onSaved, onCancel }: { org: string; role: string | null; existing?: Existing; onSaved: (slug: string, version: number) => void; onCancel: () => void }) {
  const qc = useQueryClient();
  const envs = useSimEnvs(org);
  const experiments = useExperiments(org);
  const { models } = useModels(org);
  const [form, setForm] = useState<Form | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const created = useRef<string | null>(null);

  const env = envs.data?.find((e) => e.slug === form?.environment);
  const scenario: SimScenario | undefined = env?.scenarios?.find((s) => scenarioKey(s) === form?.scenario);

  // Start from the first ready environment, or from the version being changed.
  useEffect(() => {
    if (form || !envs.data) return;
    if (existing) {
      setForm(formFromSpec(existing.version.spec, existing.exp));
      return;
    }
    const first = envs.data.find((e) => e.state === "ready");
    setForm(blankForm(first, first?.scenarios?.[0]));
  }, [envs.data, existing, form]);

  const fields = useMemo(() => (scenario ? fieldsFor(scenario.parameters_schema) : []), [scenario]);
  const built = useMemo(() => (form ? buildSpec(form, env, scenario) : null), [form, env, scenario]);
  const slugTaken = !existing && !!form && !!experiments.data?.some((e) => e.slug === form.slug);
  const errors: Record<string, string> = { ...(built?.problems.fields ?? {}), ...(slugTaken ? { slug: "An experiment with this name already exists." } : {}) };

  const save = useMutation({
    mutationFn: async () => {
      if (!form || !built?.spec) throw new Error("The form is not complete.");
      const slug = existing?.exp.slug ?? form.slug;
      if (!existing && created.current !== slug) {
        await api(`${orgPath(org)}/experiments`, { method: "POST", body: JSON.stringify({ slug, name: form.name.trim(), description: form.description.trim() }) });
        created.current = slug;
      }
      return api<ExperimentVersion>(`${orgPath(org)}/experiments/${slug}/versions`, { method: "POST", body: JSON.stringify({ spec: built.spec, notes: form.notes }) });
    },
    onSuccess: async (v) => {
      await qc.invalidateQueries({ queryKey: ["experiments", org] });
      onSaved(existing?.exp.slug ?? form!.slug, v.number);
    },
  });

  if (role === "viewer")
    return (
      <>
        <PageHeader title="New experiment" />
        <Notice tone="info">Only engineers can configure experiments. You can read every experiment and ask for a run of any version.</Notice>
      </>
    );
  if (envs.isLoading || !form) return <p className="text-[13px] text-muted">Loading simulation environments…</p>;
  if (envs.error) return <ErrorNotice error={envs.error} org={org} onReload={() => void envs.refetch()} />;
  const ready = envs.data!.filter((e) => e.state === "ready");

  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });
  const setArm = (i: number, patch: Partial<Form["arms"][number]>) => set({ arms: form.arms.map((a, j) => (j === i ? { ...a, ...patch } : a)) });
  const pick = (e: SimEnv, s: SimScenario) => {
    const fresh = blankForm(e, s);
    set({ environment: e.slug, scenario: scenarioKey(s), arms: fresh.arms, rules: fresh.rules, keep: fresh.keep, varySeed: fresh.varySeed, model: "" });
  };
  const trials = form.arms.length * (Number(form.repetitions) || 0);
  const mcap = scenario ? mcapArtifact(scenario) : null;
  const show = submitted;

  return (
    <>
      <Crumbs items={[{ label: "Experiments", href: `/experiments?org=${org}` }, ...(existing ? [{ label: existing.exp.name, href: `/experiments?org=${org}&exp=${existing.exp.slug}` }] : []), { label: existing ? "Changed version" : "New experiment" }]} />
      <PageHeader
        title={existing ? `Change ${existing.exp.name}` : "New experiment"}
        subtitle={existing ? `Saved as version ${existing.exp.versions.length + 1}. Version ${existing.version.number} stays exactly as it is.` : "Describe what to test, how the setups differ and what counts as a pass. Nothing runs until an engineer approves it."}
      />
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(true);
          if (built?.spec && !slugTaken) save.mutate();
        }}
      >
        <Section n={1} title="What do you want to test?" help={existing ? "The environment and scenario are fixed for an experiment. A different scenario is a different experiment." : undefined}>
          {!existing && (
            <div className="max-w-md text-[13px]">
              <label>
                <span className="mb-1 block text-muted">Name</span>
                <input className="field w-full" value={form.name} onChange={(e) => set({ name: e.target.value, slug: slugify(e.target.value) })} aria-invalid={(show && (!!errors.name || !!errors.slug)) || undefined} aria-describedby={show && (errors.name || errors.slug) ? `${errId("name")} ${errId("slug")}` : undefined} placeholder="For example: Stop when commands are lost" />
              </label>
              <FieldError k="name" errors={errors} show={show} />
              <FieldError k="slug" errors={errors} show={show} />
            </div>
          )}
          {envs.data!.length === 0 && (
            <Notice tone="info">
              No simulation environment is connected to this workspace yet. Connect one and run discovery in the{" "}
              <Link className="underline" href={`/hardware?org=${org}`}>
                Hardware Hub
              </Link>
              , then come back.
            </Notice>
          )}
          {envs.data!.length > 0 && (
            <fieldset disabled={!!existing} className="space-y-2">
              <legend className="mb-1 text-[13px] text-muted">Simulation environment and scenario</legend>
              {envs.data!.map((e) => {
                const st = ENV_STATE[e.state];
                return (
                  <div key={e.slug} className={clsx("rounded-[5px] border px-3 py-2", e.slug === form.environment ? "border-accent" : "border-line")}>
                    <div className="flex flex-wrap items-center gap-2 text-[13px]">
                      <span className="font-medium">{e.name}</span>
                      <Badge tone={st.tone}>{st.text}</Badge>
                      {e.simulator && <span className="text-muted">{String(e.simulator.name)}</span>}
                      {e.state !== "ready" && !existing && (
                        <button type="button" className="btn ml-auto py-0.5" onClick={() => void envs.refetch()}>
                          Check again
                        </button>
                      )}
                    </div>
                    {e.simulator_description && <p className="mt-0.5 text-[12px] text-muted">{e.simulator_description}</p>}
                    {e.state !== "ready" && (
                      <p className="mt-1 text-[12px] text-muted">
                        {e.message ?? st.fix} {st.fix && e.message ? st.fix : ""}
                      </p>
                    )}
                    {e.state === "ready" && (
                      <div role="radiogroup" aria-label={`Scenarios on ${e.name}`} className="mt-2 space-y-1">
                        {(e.scenarios ?? []).map((s) => (
                          <label key={scenarioKey(s)} className={clsx("flex cursor-pointer items-start gap-2 rounded-sm px-2 py-1.5 text-[13px] hover:bg-sunken", scenarioKey(s) === form.scenario && e.slug === form.environment && "bg-sunken")}>
                            <input type="radio" name="scenario" className="mt-1" checked={scenarioKey(s) === form.scenario && e.slug === form.environment} onChange={() => pick(e, s)} />
                            <span>
                              <span className="font-medium">{s.title}</span>
                              <span className="ml-2 text-faint">version {s.version}</span>
                              {s.description && <span className="block text-[12px] text-muted">{s.description}</span>}
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </fieldset>
          )}
          {ready.length === 0 && envs.data!.length > 0 && <Notice tone="warn">No environment is ready, so nothing can be configured yet. Fix one above, then check again.</Notice>}
          {!existing && (
            <label className="block max-w-xl text-[13px]">
              <span className="mb-1 block text-muted">Why are you running it? (optional)</span>
              <textarea className="field w-full" rows={2} value={form.description} onChange={(e) => set({ description: e.target.value })} />
            </label>
          )}
        </Section>

        {scenario && env && (
          <>
            <Section n={2} title="Setups to compare" help="Each column is one setup. Values that are the same in every setup are kept as shared conditions; only the differences belong to a setup.">
              <div className="overflow-x-auto" role="region" aria-label="Setups and their parameters" tabIndex={0}>
                <table className="w-full min-w-[480px] border-collapse text-[13px]">
                  <thead>
                    <tr className="border-b border-line text-left align-bottom">
                      <th scope="col" className="w-64 px-2 py-1.5 text-xs font-medium text-muted">
                        Parameter
                      </th>
                      {form.arms.map((a, i) => (
                        <th key={i} scope="col" className="px-2 py-1.5 align-top">
                          <label className="block text-xs font-medium text-muted">
                            Setup name
                            <input
                              className="field mt-1 w-full min-w-32 font-normal text-ink"
                              value={a.title}
                              aria-invalid={show && !!errors[`arm.${i}.title`]}
                              onChange={(e) => setArm(i, { title: e.target.value, key: armKey(e.target.value, form.arms.filter((_, j) => j !== i).map((x) => x.key)) })}
                            />
                          </label>
                          <FieldError k={`arm.${i}.title`} errors={errors} show={show} />
                          <div className="mt-1 flex items-center gap-2">
                            <label className="flex items-center gap-1 text-xs font-normal text-muted">
                              <input type="checkbox" checked={a.role === "baseline"} onChange={(e) => set({ arms: form.arms.map((x, j) => ({ ...x, role: j === i && e.target.checked ? "baseline" : "candidate" })) })} />
                              Baseline
                            </label>
                            {form.arms.length > 1 && (
                              <button type="button" className="ml-auto text-xs font-normal text-accent hover:underline" onClick={() => set({ arms: form.arms.filter((_, j) => j !== i) })}>
                                Remove {a.title || "setup"}
                              </button>
                            )}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {fields.map((f) => (
                      <tr key={f.key} className="align-top">
                        <th scope="row" className="px-2 py-2 text-left font-normal">
                          <span className="block">{f.label}</span>
                          {f.required && <span className="text-[11px] text-faint">required</span>}
                          {f.help && <span className="block text-[12px] text-muted">{f.help}</span>}
                        </th>
                        {form.arms.map((a, i) => (
                          <td key={i} className="px-2 py-2">
                            <ParamControl f={f} value={a.values[f.key]} label={`${f.label}, ${a.title || `setup ${i + 1}`}`} invalid={show && !!errors[`arm.${i}.${f.key}`]} errId={errId(`arm.${i}.${f.key}`)} onChange={(v) => setArm(i, { values: { ...a.values, [f.key]: v } })} />
                            <FieldError k={`arm.${i}.${f.key}`} errors={errors} show={show} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {form.arms.length < 6 && (
                <button type="button" className="btn" onClick={() => {
                  const title = `Setup ${form.arms.length + 1}`;
                  set({ arms: [...form.arms, { key: armKey(title, form.arms.map((a) => a.key)), title, role: "candidate", values: { ...(form.arms.at(-1)?.values ?? {}) } }] });
                }}>
                  Add a setup
                </button>
              )}
            </Section>

            <Section n={3} title="How many times, and what counts as a pass?">
              <div className="flex flex-wrap items-end gap-4">
                <label className="text-[13px]">
                  <span className="mb-1 block text-muted">Repetitions per setup</span>
                  <input className="field w-24" inputMode="numeric" value={form.repetitions} aria-invalid={show && !!errors.repetitions} onChange={(e) => set({ repetitions: e.target.value })} />
                </label>
                {hasSeed(scenario.parameters_schema) && (
                  <label className="flex items-center gap-2 pb-1.5 text-[13px]">
                    <input type="checkbox" checked={form.varySeed} onChange={(e) => set({ varySeed: e.target.checked })} />
                    Use a different random seed for each repetition (1 to {Number(form.repetitions) || "n"})
                  </label>
                )}
              </div>
              <FieldError k="repetitions" errors={errors} show={show} />
              <div className="space-y-2">
                <p className="text-[13px] text-muted">A trial passes when every rule below holds. The verdict is the engine&apos;s, over what the host measured.</p>
                {form.rules.map((r, i) => (
                  <div key={i} className="flex flex-wrap items-start gap-2 text-[13px]">
                    <label>
                      <span className="sr-only">Measurement for rule {i + 1}</span>
                      <select className="field" value={r.measurement} onChange={(e) => set({ rules: form.rules.map((x, j) => (j === i ? { ...x, measurement: e.target.value } : x)) })}>
                        {(scenario.outputs as { name: string }[]).map((o) => (
                          <option key={o.name} value={o.name}>
                            {measureLabel(o.name)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span className="sr-only">Comparison for rule {i + 1}</span>
                      <select className="field" value={r.op} onChange={(e) => set({ rules: form.rules.map((x, j) => (j === i ? { ...x, op: e.target.value as RuleOp } : x)) })}>
                        {(Object.keys(OP_WORDS) as RuleOp[]).map((op) => (
                          <option key={op} value={op}>
                            {OP_WORDS[op]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span>
                      <label>
                        <span className="sr-only">{r.op === "between" ? "Lower bound" : "Value"} for rule {i + 1}</span>
                        <input className="field w-24" inputMode="decimal" value={r.value} aria-invalid={show && !!errors[`rule.${i}.value`]} onChange={(e) => set({ rules: form.rules.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)) })} />
                      </label>
                      <FieldError k={`rule.${i}.value`} errors={errors} show={show} />
                    </span>
                    {r.op === "between" && (
                      <span>
                        <span className="mr-2 text-muted">and</span>
                        <label>
                          <span className="sr-only">Upper bound for rule {i + 1}</span>
                          <input className="field w-24" inputMode="decimal" value={r.max} aria-invalid={show && !!errors[`rule.${i}.max`]} onChange={(e) => set({ rules: form.rules.map((x, j) => (j === i ? { ...x, max: e.target.value } : x)) })} />
                        </label>
                        <FieldError k={`rule.${i}.max`} errors={errors} show={show} />
                      </span>
                    )}
                    <span className="pt-1.5 text-muted">{unitOf(scenario, r.measurement)}</span>
                    {form.rules.length > 1 && (
                      <button type="button" className="pt-1.5 text-accent hover:underline" onClick={() => set({ rules: form.rules.filter((_, j) => j !== i) })}>
                        Remove rule {i + 1}
                      </button>
                    )}
                  </div>
                ))}
                {form.rules.some((r) => r.value !== "") && <p className="text-[12px] text-muted">Pass when {form.rules.filter((r) => r.value !== "").map((r) => ruleSentence(scenario, r)).join(" and ")}.</p>}
                <button type="button" className="btn" onClick={() => set({ rules: [...form.rules, { measurement: (scenario.outputs[0] as { name: string }).name, op: "le", value: "", max: "" }] })}>
                  Add a rule
                </button>
              </div>
            </Section>

            <Section n={4} title="What should be kept?" help="Files are fetched from the host after each trial and checked against the digest the host reported before they are stored.">
              {(scenario.artifacts as { name: string; description?: string; media_type?: string }[]).length === 0 && <p className="text-[13px] text-muted">This scenario leaves no files. The measurements are always kept.</p>}
              {(scenario.artifacts as { name: string; description?: string; media_type?: string }[]).map((a) => (
                <label key={a.name} className="flex items-start gap-2 text-[13px]">
                  <input type="checkbox" className="mt-1" checked={form.keep.includes(a.name)} onChange={(e) => set({ keep: e.target.checked ? [...form.keep, a.name] : form.keep.filter((n) => n !== a.name) })} />
                  <span>
                    {humanize(a.name)}
                    <span className="ml-2 text-faint">{a.media_type}</span>
                    {a.description && <span className="block text-[12px] text-muted">{a.description}</span>}
                  </span>
                </label>
              ))}
              {mcap && form.keep.includes(mcap) && (
                <label className="block max-w-md text-[13px]">
                  <span className="mb-1 block text-muted">Show the recording in the Digital twin on this robot model</span>
                  <select className="field w-full" value={form.model} onChange={(e) => set({ model: e.target.value })}>
                    <option value="">Keep the file only (no Digital twin)</option>
                    {models.map((m) => (
                      <option key={m.ref} value={m.ref}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                  {models.length === 0 && <span className="mt-1 block text-[12px] text-muted">No robot model is registered in this workspace yet. Add one in a project&apos;s Digital twin to see recordings move.</span>}
                </label>
              )}
            </Section>

            <Section n={5} title="Who is it for?" help="So a result can be traced to the exact software it ran, and so the right person approves it.">
              <div className="space-y-2">
                {form.software.map((s, i) => (
                  <div key={i} className="flex flex-wrap items-start gap-2 text-[13px]">
                    <span>
                      <label>
                        <span className="mb-1 block text-muted">{i === 0 ? "Software under test" : "Also"}</span>
                        <input className="field w-52" value={s.name} aria-invalid={show && !!errors[`software.${i}.name`]} placeholder="For example: controller" onChange={(e) => set({ software: form.software.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
                      </label>
                      <FieldError k={`software.${i}.name`} errors={errors} show={show} />
                    </span>
                    <span>
                      <label>
                        <span className="mb-1 block text-muted">Revision</span>
                        <input className="field num w-56" value={s.revision} aria-invalid={show && !!errors[`software.${i}.revision`]} placeholder="commit or tag" onChange={(e) => set({ software: form.software.map((x, j) => (j === i ? { ...x, revision: e.target.value } : x)) })} />
                      </label>
                      <FieldError k={`software.${i}.revision`} errors={errors} show={show} />
                    </span>
                    {form.software.length > 1 && (
                      <button type="button" className="mt-6 text-accent hover:underline" onClick={() => set({ software: form.software.filter((_, j) => j !== i) })}>
                        Remove {s.name || "software"}
                      </button>
                    )}
                  </div>
                ))}
                <button type="button" className="btn" onClick={() => set({ software: [...form.software, { name: "", revision: "" }] })}>
                  Add software
                </button>
              </div>
              <div className="flex flex-wrap items-end gap-4 border-t border-line pt-3 text-[13px]">
                <label>
                  <span className="mb-1 block text-muted">Approver</span>
                  <select className="field" value={form.approverRole} onChange={(e) => set({ approverRole: e.target.value as "engineer" | "admin" })}>
                    <option value="engineer">Any engineer</option>
                    <option value="admin">An admin</option>
                  </select>
                </label>
                <p className="self-end pb-1.5 text-sm text-muted">A second person must approve this version before it can run.</p>
              </div>
            </Section>
          </>
        )}

        {save.error && <ErrorNotice error={save.error} org={org} exp={existing?.exp.slug} />}
        {submitted && built && !built.spec && (
          <Notice tone="warn">
            Some values need attention: {Object.keys(errors).length + built.problems.form.length} to fix above.{built.problems.form.length > 0 && ` ${built.problems.form.join(" ")}`}
          </Notice>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn btn-primary" type="submit" disabled={save.isPending || !scenario}>
            {save.isPending ? "Saving…" : existing ? "Save as a new version" : "Save experiment"}
          </button>
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
          {scenario && trials > 0 && (
            <span className="text-[12px] text-muted">
              Each run will be {trials} trial{trials === 1 ? "" : "s"} ({form.arms.length} setup{form.arms.length === 1 ? "" : "s"} × {Number(form.repetitions) || 0}), at most {Math.ceil(trials * scenario.max_duration_s)} s on the host.
            </span>
          )}
        </div>
      </form>
    </>
  );
}

function ParamControl({ f, value, label, invalid, errId: eid, onChange }: { f: Field; value: string | boolean | undefined; label: string; invalid: boolean; errId: string; onChange: (v: string | boolean) => void }) {
  const common = { "aria-label": label, "aria-invalid": invalid || undefined, "aria-describedby": invalid ? eid : undefined } as const;
  if (f.kind === "boolean")
    return (
      <select className="field w-full min-w-28" {...common} value={value === undefined ? "" : String(value)} onChange={(e) => onChange(e.target.value === "" ? "" : e.target.value === "true")}>
        {!f.required && <option value="">Host default</option>}
        {f.required && value === undefined && <option value="">Choose…</option>}
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    );
  if (f.kind === "choice")
    return (
      <select className="field w-full min-w-28" {...common} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
        {!f.required && <option value="">Host default</option>}
        {f.choices?.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    );
  return (
    <input
      className="field w-full min-w-28"
      {...common}
      inputMode={f.kind === "text" ? undefined : "decimal"}
      value={String(value ?? "")}
      placeholder={f.default !== undefined ? `Default ${String(f.default)}` : f.min !== undefined && f.max !== undefined ? `${f.min} to ${f.max}` : undefined}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

