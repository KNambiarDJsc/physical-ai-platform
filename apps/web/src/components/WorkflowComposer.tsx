"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { api, orgPath, type Workflow } from "@/lib/api/client";
import { actionsOf, buildDefinition, capability, conditionSentence, inputFields, openOutput, outputFields, type ComposeForm } from "@/lib/compose";
import { OP_WORDS, humanize, slugify, type RuleOp } from "@/lib/experiments";
import { Notice, Panel } from "./AppShell";
import { useDevices, useEnvironments } from "./Workspace";

const blank = (env: string): ComposeForm => ({
  name: "",
  environment: env,
  steps: [{ device: "", action: "", title: "", values: {} }],
  verify: true,
  claimStep: 0,
  evidence: [],
  conditions: [],
});

/**
 * Compose a workflow across the instruments an environment's discovery found: ordered actions, each action's inputs
 * from its own schema, and how the engine verifies the result (which step's report is the claim, which other step's
 * output is the independent evidence, and the conditions). Only simulated environments can run (D-026).
 */
export function WorkflowComposer({ org }: { org: string }) {
  const qc = useQueryClient();
  const envs = useEnvironments(org);
  const all = useDevices(org);
  const simulated = (envs.data ?? []).filter((e) => e.kind === "simulated");
  const [form, setForm] = useState<ComposeForm>(() => blank(""));
  const env = form.environment || simulated[0]?.slug || "";
  const devices = useMemo(() => (all.data ?? []).filter((d) => d.environment === env && d.present && actionsOf(d).length > 0), [all.data, env]);
  const [submitted, setSubmitted] = useState(false);
  const [made, setMade] = useState<Workflow | null>(null);
  const built = buildDefinition({ ...form, environment: env }, devices);
  const err = (k: string) => (submitted ? built.problems.fields[k] : undefined);
  const set = (p: Partial<ComposeForm>) => setForm({ ...form, ...p });
  const setStep = (i: number, p: Partial<ComposeForm["steps"][number]>) => set({ steps: form.steps.map((s, j) => (j === i ? { ...s, ...p } : s)) });
  const create = useMutation({
    mutationFn: () => api<Workflow>(`${orgPath(org)}/workflows`, { method: "POST", body: JSON.stringify({ slug: slugify(form.name), name: form.name.trim(), environment: env, definition: built.definition }) }),
    onSuccess: (w) => {
      setMade(w);
      void qc.invalidateQueries({ queryKey: ["workflows", org] });
    },
  });
  if (simulated.length === 0) return null;
  const stepLabel = (i: number) => {
    const s = form.steps[i];
    return s?.action ? `${i + 1}. ${humanize(s.action)} (${s.device})` : `Step ${i + 1}`;
  };

  return (
    <Panel title="Compose a workflow from instruments">
      <form
        className="space-y-4 text-[13px]"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(true);
          setMade(null);
          if (built.definition) create.mutate();
        }}
      >
        <p className="max-w-3xl text-muted">Put actions of different instruments in order. Then say how the result is checked: one step&apos;s report is the claim, another step&apos;s measurement is the independent evidence, and the engine judges the conditions.</p>
        <div className="flex flex-wrap items-end gap-3">
          <label>
            <span className="mb-1 block text-muted">Name</span>
            <input className="field w-64" value={form.name} aria-invalid={!!err("name")} onChange={(e) => set({ name: e.target.value })} placeholder="For example: Two dispenses then weigh" />
          </label>
          <label>
            <span className="mb-1 block text-muted">Environment</span>
            <select className="field" value={env} onChange={(e) => set({ ...blank(e.target.value), name: form.name })}>
              {simulated.map((e) => (
                <option key={e.slug} value={e.slug}>
                  {e.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {err("name") && <p className="text-[12px] text-bad">{err("name")}</p>}
        {devices.length === 0 && <Notice tone="info">No instruments have been discovered in this environment yet. Run discovery in the <Link className="underline" href={`/hardware?org=${org}`}>Hardware Hub</Link>.</Notice>}

        <ol className="space-y-2" aria-label="Steps">
          {form.steps.map((s, i) => {
            const cap = capability(devices, s);
            return (
              <li key={i} className="rounded-[5px] border border-line p-3">
                <div className="flex flex-wrap items-end gap-3">
                  <span className="num w-6 pb-1.5 text-faint">{i + 1}</span>
                  <label>
                    <span className="mb-1 block text-muted">Instrument</span>
                    <select className="field" value={s.device} aria-invalid={!!err(`step.${i}.device`)} onChange={(e) => setStep(i, { device: e.target.value, action: "", values: {} })}>
                      <option value="">Choose…</option>
                      {devices.map((d) => (
                        <option key={d.key} value={d.key}>
                          {d.title || d.key}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span className="mb-1 block text-muted">Action</span>
                    <select className="field" value={s.action} aria-invalid={!!err(`step.${i}.action`)} onChange={(e) => setStep(i, { action: e.target.value, values: {} })} disabled={!s.device}>
                      <option value="">Choose…</option>
                      {actionsOf(devices.find((d) => d.key === s.device)).map((c) => (
                        <option key={c.name} value={c.name}>
                          {humanize(c.name)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {inputFields(cap).map((f) => (
                    <label key={f.key}>
                      <span className="mb-1 block text-muted">{f.label}</span>
                      <input className="field w-28" inputMode="decimal" value={String(s.values[f.key] ?? "")} aria-invalid={!!err(`step.${i}.${f.key}`)} placeholder={f.min !== undefined && f.max !== undefined ? `${f.min} to ${f.max}` : undefined} onChange={(e) => setStep(i, { values: { ...s.values, [f.key]: e.target.value } })} />
                    </label>
                  ))}
                  <span className="ml-auto flex gap-2 pb-1.5">
                    {i > 0 && (
                      <button type="button" className="text-accent hover:underline" onClick={() => { const st = [...form.steps]; [st[i - 1], st[i]] = [st[i]!, st[i - 1]!]; set({ steps: st }); }}>
                        Move step {i + 1} up
                      </button>
                    )}
                    {form.steps.length > 1 && (
                      <button type="button" className="text-accent hover:underline" onClick={() => set({ steps: form.steps.filter((_, j) => j !== i), evidence: [], conditions: [], claimStep: 0 })}>
                        Remove step {i + 1}
                      </button>
                    )}
                  </span>
                </div>
                {[err(`step.${i}.device`), err(`step.${i}.action`), ...inputFields(cap).map((f) => err(`step.${i}.${f.key}`))].filter(Boolean).map((m, k) => (
                  <p key={k} className="mt-1 text-[12px] text-bad">
                    {m}
                  </p>
                ))}
              </li>
            );
          })}
        </ol>
        <button type="button" className="btn" onClick={() => set({ steps: [...form.steps, { device: "", action: "", title: "", values: {} }] })}>
          Add a step
        </button>

        <fieldset className="space-y-3 border-t border-line pt-3">
          <legend className="sr-only">Verification</legend>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.verify} onChange={(e) => set({ verify: e.target.checked })} />
            The engine verifies the result
          </label>
          {form.verify && (
            <>
              <label className="block">
                <span className="mb-1 block text-muted">Whose report is the claim?</span>
                <select className="field" value={form.claimStep} onChange={(e) => set({ claimStep: Number(e.target.value) })}>
                  {form.steps.map((_, i) => (
                    <option key={i} value={i}>
                      {stepLabel(i)}
                    </option>
                  ))}
                </select>
              </label>
              <div className="space-y-2">
                <span className="block text-muted">Independent evidence</span>
                {form.evidence.map((e, i) => {
                  const cap = capability(devices, form.steps[e.step] ?? { device: "", action: "", title: "", values: {} });
                  const fields = outputFields(cap);
                  const typed = fields.length === 0 && openOutput(cap);
                  const upd = (p: Partial<ComposeForm["evidence"][number]>) => set({ evidence: form.evidence.map((x, j) => (j === i ? { ...x, ...p } : x)) });
                  return (
                    <div key={i} className="flex flex-wrap items-end gap-2">
                      <label>
                        <span className="mb-1 block text-[12px] text-muted">Measured by</span>
                        <select className="field" value={e.step} aria-invalid={!!err(`evidence.${i}.step`)} onChange={(ev) => upd({ step: Number(ev.target.value), field: "" })}>
                          {form.steps.map((_, k) => (
                            <option key={k} value={k}>
                              {stepLabel(k)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span className="mb-1 block text-[12px] text-muted">Value</span>
                        {typed ? (
                          <input className="field num w-36" value={e.field} aria-invalid={!!err(`evidence.${i}.field`)} aria-describedby={`open-${i}`} onChange={(ev) => upd({ field: ev.target.value.trim() })} placeholder="e.g. mass_g" />
                        ) : (
                          <select className="field" value={e.field} aria-invalid={!!err(`evidence.${i}.field`)} onChange={(ev) => upd({ field: ev.target.value })}>
                            <option value="">Choose…</option>
                            {fields.map((f) => (
                              <option key={f} value={f}>
                                {humanize(f)}
                              </option>
                            ))}
                          </select>
                        )}
                      </label>
                      {typed && (
                        <p id={`open-${i}`} className="w-full text-[12px] text-muted">
                          This action does not declare the names of what it returns. Type the field of its answer that holds the value; if it is not there, the engine reports the evidence as missing.
                        </p>
                      )}
                      <label>
                        <span className="mb-1 block text-[12px] text-muted">Signal</span>
                        <input className="field num w-40" value={e.signal} aria-invalid={!!err(`evidence.${i}.signal`)} onChange={(ev) => upd({ signal: ev.target.value })} placeholder="vessel.net_mass" />
                      </label>
                      <label>
                        <span className="mb-1 block text-[12px] text-muted">Unit</span>
                        <input className="field w-16" value={e.unit} onChange={(ev) => upd({ unit: ev.target.value })} />
                      </label>
                      {[err(`evidence.${i}.step`), err(`evidence.${i}.field`), err(`evidence.${i}.signal`)].filter(Boolean).map((m, k) => (
                        <p key={k} className="w-full text-[12px] text-bad">
                          {m}
                        </p>
                      ))}
                    </div>
                  );
                })}
                <button type="button" className="btn" onClick={() => set({ evidence: [...form.evidence, { step: form.steps.length - 1, field: "", signal: "", unit: "" }] })}>
                  Add evidence
                </button>
              </div>
              <div className="space-y-2">
                <span className="block text-muted">The result passes when</span>
                {form.conditions.map((c, i) => {
                  const upd = (p: Partial<ComposeForm["conditions"][number]>) => set({ conditions: form.conditions.map((x, j) => (j === i ? { ...x, ...p } : x)) });
                  return (
                    <div key={i} className="flex flex-wrap items-end gap-2">
                      <label>
                        <span className="sr-only">Evidence for condition {i + 1}</span>
                        <select className="field" value={c.evidence} onChange={(ev) => upd({ evidence: Number(ev.target.value) })}>
                          {form.evidence.map((e, k) => (
                            <option key={k} value={k}>
                              {e.field ? humanize(e.field) : `Evidence ${k + 1}`}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span className="sr-only">Comparison for condition {i + 1}</span>
                        <select className="field" value={c.op} onChange={(ev) => upd({ op: ev.target.value as RuleOp })}>
                          {(Object.keys(OP_WORDS) as RuleOp[]).map((op) => (
                            <option key={op} value={op}>
                              {OP_WORDS[op]}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span className="sr-only">{c.op === "between" ? "Lower bound" : "Value"} for condition {i + 1}</span>
                        <input className="field w-24" inputMode="decimal" value={c.value} aria-invalid={!!err(`condition.${i}.value`)} onChange={(ev) => upd({ value: ev.target.value })} />
                      </label>
                      {c.op === "between" && (
                        <label>
                          <span className="sr-only">Upper bound for condition {i + 1}</span>
                          <input className="field w-24" inputMode="decimal" value={c.max} aria-invalid={!!err(`condition.${i}.max`)} onChange={(ev) => upd({ max: ev.target.value })} />
                        </label>
                      )}
                      <span className="pb-1.5 text-muted">{form.evidence[c.evidence]?.unit}</span>
                      {c.value && <span className="w-full text-[12px] text-muted">Passes when {conditionSentence({ ...form, environment: env }, c)}.</span>}
                    </div>
                  );
                })}
                <button type="button" className="btn" disabled={form.evidence.length === 0} onClick={() => set({ conditions: [...form.conditions, { evidence: 0, op: "between", value: "", max: "" }] })}>
                  Add a condition
                </button>
              </div>
            </>
          )}
        </fieldset>

        {submitted && !built.definition && (
          <Notice tone="warn">
            Some values need attention.{built.problems.form.length > 0 && ` ${built.problems.form.join(" ")}`}
          </Notice>
        )}
        {create.error && <Notice tone="bad">{create.error.message}</Notice>}
        {made && (
          <p role="status" className="text-muted">
            Saved <span className="num text-ink">{made.slug}</span>.{" "}
            <Link className="text-accent underline" href={`/workbench?org=${org}&workflow=${made.slug}`}>
              Run it in the Workbench
            </Link>
            .
          </p>
        )}
        <button className="btn btn-primary" type="submit" disabled={create.isPending}>
          {create.isPending ? "Saving…" : "Save workflow"}
        </button>
      </form>
    </Panel>
  );
}
