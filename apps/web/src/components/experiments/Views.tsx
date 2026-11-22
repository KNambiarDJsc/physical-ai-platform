"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api, download, orgPath } from "@/lib/api/client";
import {
  armSentence,
  failureHelp,
  fieldsFor,
  humanize,
  measureLabel,
  measured,
  person,
  requestStatus,
  shortSum,
  trialWords,
  unitOf,
  verdictCounts,
  type ExperimentOut,
  type ExperimentRequest,
  type ExperimentRequestDetail,
  type ExperimentVersion,
  type SimScenario,
  type TrialResult,
} from "@/lib/experiments";
import { Notice, PageHeader, Panel } from "../AppShell";
import { Badge, Table, Td, Time } from "../ui";
import { VerdictBadge } from "../Workbench";
import { ReleaseVerdict } from "./ReleaseVerdict";
import { Crumbs, ErrorNotice, Progress, SimulatedBadge, StageRail, useExperiments, useRequest, useSimEnvs } from "./common";

type Spec = {
  environment: string;
  simulator: { kind: string; name: string };
  scenario: { id: string; version: string };
  model?: { project: string; model: string; version: number };
  software: { name: string; revision: string }[];
  initial_conditions: Record<string, unknown>;
  seeds: number[];
  repetitions: number;
  arms: { key: string; title?: string; role: "baseline" | "candidate"; parameters: Record<string, unknown> }[];
  limits: { max_trials: number; max_wall_time_s: number };
  observations: { measurements: string[]; artifacts: string[]; recording?: string };
  contract: { name: string; version: string; conditions: { name: string; measurement: string }[] };
  approval: { role: string; distinct_approver: boolean };
};

const asSpec = (s: Record<string, unknown>) => s as unknown as Spec;
const asScenario = (s: Record<string, unknown>) => s as unknown as SimScenario;
const show = (v: unknown): string => (v === undefined ? "Host default" : typeof v === "boolean" ? (v ? "Yes" : "No") : String(v));

// ------------------------------------------------------------------------------------------- spec in words

/** One version of an experiment, described the way a person would: what, with which setups, judged how. */
export function SpecSummary({ spec: raw, scenario: rawScenario, envName }: { spec: Record<string, unknown>; scenario: Record<string, unknown>; envName?: string }) {
  const spec = asSpec(raw);
  const sc = asScenario(rawScenario);
  const fields = fieldsFor(sc.parameters_schema).filter((f) => spec.arms.some((a) => f.key in a.parameters || f.key in spec.initial_conditions));
  const value = (a: Spec["arms"][number], k: string) => (k in a.parameters ? a.parameters[k] : spec.initial_conditions[k]);
  // What differs between the setups is the point of the comparison, so it comes first.
  const rowsOf = fields
    .map((f) => {
      const vals = spec.arms.map((a) => value(a, f.key));
      return { f, vals, differs: new Set(vals.map(show)).size > 1 };
    })
    .sort((a, b) => Number(b.differs) - Number(a.differs));
  return (
    <div className="space-y-4 text-[13px]">
      <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-1.5">
        <dt className="text-muted">Tests</dt>
        <dd>
          <span className="font-medium">{sc.title}</span>
          <span className="text-faint"> · version {spec.scenario.version}</span>
          {sc.description && <span className="block text-[12px] text-muted">{sc.description}</span>}
        </dd>
        <dt className="text-muted">Runs on</dt>
        <dd>
          {envName ?? spec.environment} · {spec.simulator.name} <SimulatedBadge />
          {spec.simulator.kind === "selftest" && <span className="block text-[12px] text-muted">A small kinematic model that exercises the pipeline. It is not a simulator and not Gazebo.</span>}
        </dd>
        <dt className="text-muted">Trials</dt>
        <dd>
          {spec.repetitions} per setup, {spec.arms.length * spec.repetitions} in total
          {spec.seeds.length > 0 && <span className="num text-muted"> · seeds {spec.seeds.join(", ")}</span>}
        </dd>
        <dt className="text-muted">A trial passes when</dt>
        <dd>
          {spec.contract.conditions.map((c) => (
            <span key={c.name} className="block">
              {c.name}
            </span>
          ))}
        </dd>
        <dt className="text-muted">Kept</dt>
        <dd>
          Measurements{spec.observations.artifacts.length > 0 && `, ${spec.observations.artifacts.map(humanize).join(", ").toLowerCase()}`}
          {spec.model ? (
            <span className="block text-[12px] text-muted">
              The recording is shown in the Digital twin on {spec.model.model}, version {spec.model.version}.
            </span>
          ) : (
            spec.observations.artifacts.length > 0 && <span className="block text-[12px] text-muted">Files only; no Digital twin recording.</span>
          )}
        </dd>
        <dt className="text-muted">Software</dt>
        <dd>
          {spec.software.map((s) => (
            <span key={s.name} className="mr-3">
              {s.name} <span className="num text-muted">{s.revision}</span>
            </span>
          ))}
        </dd>
        <dt className="text-muted">Approval</dt>
        <dd>
          {spec.approval.role === "admin" ? "An admin" : "An engineer"}
          {spec.approval.distinct_approver ? ", other than the person who asked" : ""}
        </dd>
      </dl>
      <Table
        head={["Parameter", ...spec.arms.map((a) => `${a.title || a.key}${a.role === "baseline" && !/baseline/i.test(a.title || a.key) ? " (baseline)" : ""}`)]}
        caption="Setups and their parameters"
      >
        {rowsOf.map(({ f, vals, differs }) => (
          <tr key={f.key}>
            <Td className={differs ? "font-medium" : undefined}>
              {f.label}
              {differs && <span className="ml-2 text-[11px] font-normal text-accent">differs</span>}
            </Td>
            {vals.map((v, i) => (
              <Td key={i} className="num">
                {show(v)}
              </Td>
            ))}
          </tr>
        ))}
      </Table>
    </div>
  );
}

function Technical({ spec, sha }: { spec: Record<string, unknown>; sha: string }) {
  return (
    <details className="text-[12px] text-muted">
      <summary className="cursor-pointer select-none py-1">Technical details</summary>
      <p className="my-1">
        Checksum <span className="num break-all text-ink">{sha}</span>
      </p>
      <pre tabIndex={0} aria-label="The specification as stored" className="num max-h-72 overflow-auto rounded-sm border border-line bg-sunken p-2 text-ink">
        {JSON.stringify(spec, null, 2)}
      </pre>
    </details>
  );
}

// ----------------------------------------------------------------------------------------------------- list

export function ExperimentList({ org, role }: { org: string; role: string | null }) {
  const q = useExperiments(org);
  const waiting = (q.data ?? []).flatMap((e) => e.requests.filter((r) => r.state === "awaiting_approval").map((r) => ({ e, r })));
  const canCreate = role === "engineer" || role === "admin";
  return (
    <>
      <PageHeader
        title="Experiments"
        subtitle="Try the same scenario under different setups, have an engineer approve it, then look at what each one did."
        actions={
          canCreate && (
            <Link className="btn btn-primary" href={`/experiments?org=${org}&new=1`}>
              New experiment
            </Link>
          )
        }
      />
      {q.isLoading && <p className="text-[13px] text-muted">Loading experiments…</p>}
      {q.error && <ErrorNotice error={q.error} org={org} onReload={() => void q.refetch()} />}
      <div className="space-y-4">
        {waiting.length > 0 && (
          <Panel title={`Waiting for a decision (${waiting.length})`}>
            <Table head={["Experiment", "Version", "Asked by", "When", ""]} caption="Requests waiting for approval">
              {waiting.map(({ e, r }) => (
                <tr key={r.id}>
                  <Td>{e.name}</Td>
                  <Td className="num">{r.version}</Td>
                  <Td>{r.requested_by_me ? "You" : person(r.requested_by)}</Td>
                  <Td>
                    <Time iso={r.created_at} />
                  </Td>
                  <Td>
                    <Link className="text-accent hover:underline" href={`/experiments?org=${org}&exp=${e.slug}&request=${r.id}`}>
                      Review {e.name}
                    </Link>
                  </Td>
                </tr>
              ))}
            </Table>
          </Panel>
        )}
        {q.data && q.data.length === 0 && (
          <Panel>
            <div className="max-w-2xl space-y-3 text-[13px]">
              <p className="font-medium text-ink">No experiments yet.</p>
              <p className="text-muted">
                An experiment runs one scenario in a simulation under two or more setups (a baseline and a candidate, for instance), several times each. An engineer approves it before anything runs, the engine judges every trial against a rule you set, and the recordings open in the Digital twin.
              </p>
              {canCreate ? (
                <Link className="btn btn-primary" href={`/experiments?org=${org}&new=1`}>
                  Set up the first experiment
                </Link>
              ) : (
                <p className="text-muted">An engineer in this workspace can set one up. You can read them all and ask for a run.</p>
              )}
            </div>
          </Panel>
        )}
        {q.data && q.data.length > 0 && (
          <Panel title="All experiments">
            <Table head={["Experiment", "Versions", "Latest run", "Created"]} caption="Experiments">
              {q.data.map((e) => {
                const last = e.requests[0];
                const st = last && requestStatus(last);
                return (
                  <tr key={e.slug}>
                    <Td className="whitespace-normal">
                      <Link className="font-medium text-accent hover:underline" href={`/experiments?org=${org}&exp=${e.slug}`}>
                        {e.name}
                      </Link>
                      {e.description && <span className="block text-[12px] text-muted">{e.description}</span>}
                    </Td>
                    <Td className="num">{e.versions.length}</Td>
                    <Td>{st ? <Badge tone={st.tone}>{st.text}</Badge> : <span className="text-faint">Not run yet</span>}</Td>
                    <Td>
                      <Time iso={e.created_at} />
                    </Td>
                  </tr>
                );
              })}
            </Table>
          </Panel>
        )}
      </div>
    </>
  );
}

// ------------------------------------------------------------------------------------------ one experiment

export function ExperimentView({ org, role, slug, onRequested }: { org: string; role: string | null; slug: string; onRequested: (id: string) => void }) {
  const q = useExperiments(org);
  const envs = useSimEnvs(org);
  const qc = useQueryClient();
  const [picked, setPicked] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const exp: ExperimentOut | undefined = q.data?.find((e) => e.slug === slug);
  const ask = useMutation({
    mutationFn: (n: number) => api<ExperimentRequest>(`${orgPath(org)}/experiments/${slug}/versions/${n}/requests`, { method: "POST", body: JSON.stringify({ note }) }),
    onSuccess: async (r) => {
      await qc.invalidateQueries({ queryKey: ["experiments", org] });
      onRequested(r.id);
    },
  });
  if (q.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  if (!exp)
    return (
      <>
        <Crumbs items={[{ label: "Experiments", href: `/experiments?org=${org}` }, { label: "Not found" }]} />
        <Notice tone="warn">There is no experiment called “{slug}” in this workspace. <Link className="underline" href={`/experiments?org=${org}`}>Back to all experiments</Link>.</Notice>
      </>
    );
  const latest = exp.versions.at(-1);
  const version: ExperimentVersion | undefined = exp.versions.find((v) => v.number === (picked ?? latest?.number));
  const canEdit = role === "engineer" || role === "admin";
  return (
    <>
      <Crumbs items={[{ label: "Experiments", href: `/experiments?org=${org}` }, { label: exp.name }]} />
      <PageHeader
        title={exp.name}
        subtitle={exp.description || `Created by ${person(exp.created_by)}`}
        actions={
          canEdit && version && (
            <Link className="btn" href={`/experiments?org=${org}&exp=${exp.slug}&edit=${version.number}`}>
              Change this setup
            </Link>
          )
        }
      />
      <div className="space-y-4">
        {version && (
          <Panel
            title={
              <span className="flex flex-wrap items-center gap-3">
                Setup
                {exp.versions.length > 1 && (
                  <label className="flex items-center gap-2 text-[12px] font-normal text-muted">
                    Version
                    <select className="field py-0.5" value={version.number} onChange={(e) => setPicked(Number(e.target.value))}>
                      {exp.versions.map((v) => (
                        <option key={v.number} value={v.number}>
                          {v.number}
                          {v.number === latest?.number ? " (latest)" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <span className="text-[12px] font-normal text-muted">
                  Saved by {person(version.created_by)} · <Time iso={version.created_at} />
                </span>
              </span>
            }
          >
            <div className="space-y-4">
              <SpecSummary spec={version.spec} scenario={version.scenario} envName={envs.data?.find((e) => e.slug === version.environment)?.name} />
              <Technical spec={version.spec} sha={version.spec_sha256} />
              <div className="flex flex-wrap items-end gap-3 border-t border-line pt-3">
                <label className="text-[13px]">
                  <span className="mb-1 block text-muted">Note for the approver (optional)</span>
                  <input className="field w-72" value={note} onChange={(e) => setNote(e.target.value)} />
                </label>
                <button className="btn btn-primary" disabled={ask.isPending} onClick={() => ask.mutate(version.number)}>
                  {ask.isPending ? "Asking…" : `Ask to run version ${version.number}`}
                </button>
                <span className="pb-1.5 text-[12px] text-muted">Nothing runs until an engineer approves exactly this version.</span>
              </div>
              {ask.error && <ErrorNotice error={ask.error} org={org} exp={slug} />}
            </div>
          </Panel>
        )}
        {version && <ReleaseVerdict org={org} exp={exp} version={version} canJudge={canEdit} />}
        <Panel title="Runs">
          {exp.requests.length === 0 ? (
            <p className="text-[13px] text-muted">Not run yet. Ask for a run above; an engineer will review it.</p>
          ) : (
            <Table head={["Asked", "By", "Version", "Status", "Decided by", ""]} caption={`Runs of ${exp.name}`}>
              {exp.requests.map((r) => {
                const st = requestStatus(r);
                return (
                  <tr key={r.id}>
                    <Td>
                      <Time iso={r.created_at} />
                    </Td>
                    <Td>{r.requested_by_me ? "You" : person(r.requested_by)}</Td>
                    <Td className="num">{r.version}</Td>
                    <Td>
                      <Badge tone={st.tone}>{st.text}</Badge>
                    </Td>
                    <Td>{r.decided_by ? person(r.decided_by) : "—"}</Td>
                    <Td>
                      <Link className="text-accent hover:underline" href={`/experiments?org=${org}&exp=${exp.slug}&request=${r.id}`}>
                        Open run of version {r.version}
                      </Link>
                    </Td>
                  </tr>
                );
              })}
            </Table>
          )}
        </Panel>
      </div>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ one request

export function RequestView({ org, role, slug, id, onAskAgain }: { org: string; role: string | null; slug: string; id: string; onAskAgain: (id: string) => void }) {
  const q = useRequest(org, id);
  const envs = useSimEnvs(org);
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const d = q.data;
  const decide = useMutation({
    mutationFn: (verb: "approve" | "reject") => api<ExperimentRequestDetail>(`${orgPath(org)}/experiment-requests/${id}/${verb}`, { method: "POST", body: JSON.stringify({ spec_sha256: d!.spec_sha256, note }) }),
    onSuccess: (r) => {
      qc.setQueryData(["experiment-request", org, id], r);
      void qc.invalidateQueries({ queryKey: ["experiments", org] });
      void qc.invalidateQueries({ queryKey: ["runs", org] });
    },
  });
  const again = useMutation({
    mutationFn: () => api<ExperimentRequest>(`${orgPath(org)}/experiments/${slug}/versions/${d!.version}/requests`, { method: "POST", body: JSON.stringify({ note: "" }) }),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["experiments", org] });
      onAskAgain(r.id);
    },
  });
  if (q.isLoading) return <p className="text-[13px] text-muted">Loading this run…</p>;
  if (q.error || !d)
    return (
      <>
        <Crumbs items={[{ label: "Experiments", href: `/experiments?org=${org}` }, { label: "Run" }]} />
        <ErrorNotice error={q.error ?? new Error("not found")} org={org} onReload={() => void q.refetch()} />
      </>
    );
  const spec = asSpec(d.spec);
  const sc = asScenario(d.scenario);
  const approvalRole = spec.approval.role;
  const mayDecide = (role === "engineer" && approvalRole === "engineer") || role === "admin";
  const own = d.requested_by_me && spec.approval.distinct_approver;
  const finished = d.state === "approved" && d.trials_done >= d.trials;
  return (
    <>
      <Crumbs items={[{ label: "Experiments", href: `/experiments?org=${org}` }, { label: d.experiment_name, href: `/experiments?org=${org}&exp=${d.experiment}` }, { label: `Run of version ${d.version}` }]} />
      <PageHeader
        title={`${d.experiment_name}, version ${d.version}`}
        subtitle={
          <span>
            Asked by {d.requested_by_me ? "you" : person(d.requested_by)} · <Time iso={d.created_at} />
            {d.note && <> · “{d.note}”</>}
          </span>
        }
        actions={<StageRail detail={d} />}
      />
      <div className="space-y-4">
        {d.state === "awaiting_approval" && (
          <Panel title="Review before approving">
            <div className="space-y-4">
              <p className="max-w-3xl text-[13px] text-muted">
                An approval applies to exactly this version, with checksum <span className="num text-ink" title={d.spec_sha256}>{shortSum(d.spec_sha256)}</span>. If the version is changed afterwards it is a new version and needs its own approval. Approving queues{" "}
                <span className="text-ink">{spec.arms.length * spec.repetitions} trials</span> on {spec.simulator.name}; nothing is sent to physical hardware.
              </p>
              <SpecSummary spec={d.spec} scenario={d.scenario} envName={envs.data?.find((e) => e.slug === d.environment)?.name ?? d.environment} />
              <Technical spec={d.spec} sha={d.spec_sha256} />
              {mayDecide && !own && (
                <div className="flex flex-wrap items-end gap-3 border-t border-line pt-3">
                  <label className="text-[13px]">
                    <span className="mb-1 block text-muted">Note (optional)</span>
                    <input className="field w-72" value={note} onChange={(e) => setNote(e.target.value)} />
                  </label>
                  <button className="btn btn-primary" disabled={decide.isPending} onClick={() => decide.mutate("approve")}>
                    Approve and run {spec.arms.length * spec.repetitions} trials
                  </button>
                  <button className="btn" disabled={decide.isPending} onClick={() => decide.mutate("reject")}>
                    Reject
                  </button>
                </div>
              )}
              {mayDecide && own && <Notice tone="info">You asked for this run, and this experiment needs someone else to approve it. Another engineer in this workspace can open this page and decide.</Notice>}
              {!mayDecide && <Notice tone="info">{approvalRole === "admin" ? "An admin approves this experiment." : "Only an engineer can approve."} Your role here is {role}; you will see the result on this page once it is decided.</Notice>}
              {decide.error && <ErrorNotice error={decide.error} org={org} exp={slug} onReload={() => void q.refetch()} />}
            </div>
          </Panel>
        )}
        {d.state === "rejected" && (
          <Notice tone="warn">
            Rejected by {person(d.decided_by)}
            {d.decided_at && (
              <>
                {" "}
                on <Time iso={d.decided_at} />
              </>
            )}
            {d.decision_note && <>: “{d.decision_note}”</>}. Nothing was run.
          </Notice>
        )}
        {d.state === "approved" && (
          <Panel title="Progress">
            <div className="space-y-2">
              <Progress done={d.trials_done} total={d.trials} label="Trials finished" />
              <p className="text-[12px] text-muted">
                Approved by {person(d.decided_by)} {d.decided_at && <Time iso={d.decided_at} />}
                {d.decision_note && <> · “{d.decision_note}”</>}. {finished ? "Every trial has finished." : "Trials run one at a time on the host; this page updates by itself."}
              </p>
            </div>
          </Panel>
        )}
        {d.state === "approved" && <Results org={org} d={d} spec={spec} sc={sc} onAgain={() => again.mutate()} againBusy={again.isPending} />}
        {again.error && <ErrorNotice error={again.error} org={org} exp={slug} />}
        {d.state !== "awaiting_approval" && (
          <Panel>
            <details>
              <summary className="cursor-pointer select-none text-[13px] text-muted">What was run</summary>
              <div className="mt-3 space-y-3">
                <SpecSummary spec={d.spec} scenario={d.scenario} envName={envs.data?.find((e) => e.slug === d.environment)?.name ?? d.environment} />
                <Technical spec={d.spec} sha={d.spec_sha256} />
              </div>
            </details>
          </Panel>
        )}
      </div>
    </>
  );
}

// -------------------------------------------------------------------------------------------------- results

function Results({ org, d, spec, sc, onAgain, againBusy }: { org: string; d: ExperimentRequestDetail; spec: Spec; sc: SimScenario; onAgain: () => void; againBusy: boolean }) {
  const ruleMeasures = [...new Set(spec.contract.conditions.map((c) => c.measurement))];
  const armTitle = (key: string) => spec.arms.find((a) => a.key === key)?.title || key;
  const [dlError, setDlError] = useState<string | null>(null);
  const total = (key: string) => d.trial_results.filter((t) => t.arm === key).length;
  const baseArm = spec.arms.find((a) => a.role === "baseline")?.key ?? spec.arms[0]?.key;
  const candArm = spec.arms.find((a) => a.key !== baseArm)?.key;
  const recOf = (arm: string | undefined) => d.trial_results.find((t) => t.arm === arm && t.recording_id)?.recording_id;
  const compare3d =
    spec.model && recOf(baseArm) && recOf(candArm)
      ? `/twin?org=${org}&project=${spec.model.project}&recording=${recOf(baseArm)}&compare=${recOf(candArm)}`
      : null;
  return (
    <>
      <Panel
        title={
          <span className="flex flex-wrap items-center gap-3">
            Setups side by side
            {compare3d && (
              <Link className="text-[12px] font-normal text-accent hover:underline" href={compare3d}>
                Compare baseline and candidate in 3D
              </Link>
            )}
          </span>
        }
      >
        <p className="mb-3 max-w-3xl text-[12px] text-muted">
          The verdicts are the engine&apos;s, over the measurements the host reported. These are counts and raw values, not a statistical comparison: with few trials a difference may be chance.
        </p>
        <p className="mb-3 max-w-3xl text-[12px] text-muted" data-testid="violation-vs-regression">
          A violated trial is one run breaking the contract. It is not a release regression: that is a statistical claim the engine makes in{" "}
          <Link className="text-accent underline" href={`/releases?org=${org}`}>
            Releases
          </Link>{" "}
          from enough known outcomes per release. This run has {Math.min(...d.arms.map((a) => a.trials))}
          {new Set(d.arms.map((a) => a.trials)).size > 1 ? ` to ${Math.max(...d.arms.map((a) => a.trials))}` : ""} trial
          {Math.max(...d.arms.map((a) => a.trials)) === 1 ? "" : "s"} per setup, so no regression is claimed here.
        </p>
        <Table head={["Setup", "Engine verdicts", ...spec.observations.measurements.map((m) => `${measureLabel(m)}${unitOf(sc, m) ? ` (${unitOf(sc, m)})` : ""}`)]} caption="Setups side by side">
          {d.arms.map((a) => {
            const c = verdictCounts(a, total(a.arm));
            return (
              <tr key={a.arm}>
                <Td className="whitespace-normal">
                  <span className="font-medium">{armTitle(a.arm)}</span> {a.role === "baseline" && <Badge tone="neutral">baseline</Badge>}
                </Td>
                <Td className="whitespace-normal">
                  <span className="flex flex-wrap items-center gap-1.5">
                    {c.satisfied > 0 && <Badge tone="ok">{c.satisfied} satisfied</Badge>}
                    {c.violated > 0 && <Badge tone="bad">{c.violated} violated</Badge>}
                    {c.other > 0 && <Badge tone="unknown">{c.other} unknown</Badge>}
                    {c.pending > 0 && <Badge tone="neutral">{c.pending} pending</Badge>}
                  </span>
                  <span className="mt-0.5 block text-[12px] text-muted">{armSentence(c, total(a.arm))}</span>
                </Td>
                {spec.observations.measurements.map((m) => (
                  <Td key={m} className="num whitespace-normal">
                    {(a.values[m] ?? []).length ? (a.values[m] as unknown[]).map((v) => measured(v, "")).join(" · ") : "—"}
                  </Td>
                ))}
              </tr>
            );
          })}
        </Table>
      </Panel>
      <Panel title="Trials">
        {dlError && <Notice tone="bad">{dlError}</Notice>}
        <Table head={["Setup", "Trial", "Seed", "Status", "Verdict", ...ruleMeasures.map((m) => measureLabel(m)), "Files", ""]} caption="Every trial">
          {d.trial_results.map((t) => (
            <TrialRows key={t.id} org={org} t={t} spec={spec} sc={sc} ruleMeasures={ruleMeasures} title={armTitle(t.arm)} onDownloadError={setDlError} onAgain={onAgain} againBusy={againBusy} />
          ))}
        </Table>
      </Panel>
    </>
  );
}

function TrialRows({ org, t, spec, sc, ruleMeasures, title, onDownloadError, onAgain, againBusy }: { org: string; t: TrialResult; spec: Spec; sc: SimScenario; ruleMeasures: string[]; title: string; onDownloadError: (m: string | null) => void; onAgain: () => void; againBusy: boolean }) {
  const help = failureHelp(t);
  const cols = 7 + ruleMeasures.length;
  const project = spec.model?.project;
  const violated = t.verdict === "VIOLATED";
  return (
    <>
      <tr>
        <Td className="whitespace-normal">{title}</Td>
        <Td className="num">{t.repetition + 1}</Td>
        <Td className="num">{t.seed ?? "—"}</Td>
        <Td>{trialWords(t)}</Td>
        <Td>{t.verdict ? <VerdictBadge verdict={t.verdict} /> : "—"}</Td>
        {ruleMeasures.map((m) => (
          <Td key={m} className="num">
            {measured(t.measurements?.[m], unitOf(sc, m))}
          </Td>
        ))}
        <Td className="whitespace-normal">
          {t.artifacts.length === 0 && <span className="text-faint">—</span>}
          {t.artifacts.map((a) =>
            a.state === "stored" ? (
              <button
                key={a.name}
                className="mr-2 text-accent hover:underline"
                title={`${a.sha256} · ${a.size_bytes} bytes`}
                onClick={() => {
                  onDownloadError(null);
                  download(`${orgPath(org)}/experiment-trials/${t.id}/artifacts/${a.name}`, a.filename ?? a.name).catch(() => onDownloadError(`Could not download ${a.name}. Try again in a moment.`));
                }}
              >
                Download {a.name}
              </button>
            ) : (
              <Badge key={a.name} tone="bad">
                {a.name} rejected
              </Badge>
            ),
          )}
        </Td>
        <Td className="whitespace-normal">
          {t.recording_id && project ? (
            <Link className="text-accent hover:underline" href={`/twin?org=${org}&project=${project}&recording=${t.recording_id}`}>
              {violated ? "Investigate in Digital twin" : "Open in Digital twin"}
            </Link>
          ) : (
            <span className="text-faint">{t.state === "succeeded" && spec.model && t.capture_state === "pending" ? "Preparing recording…" : "No twin recording"}</span>
          )}
        </Td>
      </tr>
      {help && (
        <tr>
          <td colSpan={cols} className="px-2 pb-2 pt-0 text-[12px]">
            <div className="rounded-[5px] border border-bad/35 bg-bad-soft px-3 py-2 text-bad">
              <span className="font-medium">{title}, trial {t.repetition + 1}:</span> {help.what} <span className="text-ink">{help.next}</span>
              {(t.state === "failed" || t.state === "outcome_unknown") && (
                <button className="btn ml-3 py-0.5" disabled={againBusy} onClick={onAgain}>
                  Ask for a new run
                </button>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
