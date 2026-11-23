"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Play } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  orgPath,
  type Device,
  type PropertyRead,
  type Workflow,
  type WorkflowRunDetail,
  type WorkflowStep,
} from "@/lib/api/client";
import { shortDigest, timestamp } from "@/lib/format";
import { Notice } from "./AppShell";
import { KindBadge } from "./Hardware";
import { ObsState } from "./Observation";
import { RequireIdentity } from "./Identity";
import { Split } from "./Split";
import { Badge, ClassBadge, Time } from "./ui";
import { OrgSelect, RUN_STATE, useDevices, useOrg, useRuns, useWorkflows } from "./Workspace";

type Selection = { kind: "step"; position: number } | { kind: "verification" };

/** The engine's observed values as text: {"value": 0.0499, "unit": "g"} reads "0.0499 g". Formatting only. */
export function observedText(observed: unknown[] | undefined): string {
  if (!observed || observed.length === 0) return "nothing observed";
  return observed
    .map((o) => (o && typeof o === "object" && "value" in o ? `${String((o as { value: unknown }).value)}${(o as { unit?: string }).unit ? ` ${(o as { unit?: string }).unit}` : ""}` : JSON.stringify(o)))
    .join(", ");
}

const CONDITION_RESULT: Record<string, string> = { TRUE: "met", FALSE: "not met", UNDETERMINED: "undetermined" };

export function WorkbenchView() {
  return (
    <RequireIdentity>
      <Workbench />
    </RequireIdentity>
  );
}

function stateTone(s: string): "ok" | "bad" | "warn" | "unknown" | "neutral" | "accent" {
  if (s === "succeeded" || s === "completed") return "ok";
  if (s === "failed" || s === "refused") return "bad";
  if (s === "outcome_unknown") return "warn";
  if (s === "running" || s === "dispatching") return "accent";
  return "neutral";
}

export function VerdictBadge({ verdict }: { verdict: string | null | undefined }) {
  if (!verdict) return <Badge tone="neutral">not verified</Badge>;
  const tone = verdict === "SATISFIED" ? "ok" : verdict === "VIOLATED" ? "bad" : "unknown";
  return <Badge tone={tone}>{verdict.toLowerCase()}</Badge>;
}

function Workbench() {
  const { me, orgs, org, role, select } = useOrg();
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const workflows = useWorkflows(org);
  const runs = useRuns(org);
  const devices = useDevices(org);
  const [wfSlug, setWfSlug] = useState<string | null>(params.get("workflow"));
  const runId = params.get("run") ?? runs.data?.[0]?.id ?? null;
  const [sel, setSel] = useState<Selection>({ kind: "verification" });

  const run = useQuery({
    queryKey: ["run", org, runId],
    queryFn: () => api<WorkflowRunDetail>(`${orgPath(org!)}/workflow-runs/${runId}`),
    enabled: !!org && !!runId,
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.state) ? 700 : false),
  });
  const wf = workflows.data?.find((w) => w.slug === (wfSlug ?? run.data?.workflow)) ?? workflows.data?.[0];

  const setRun = (id: string) => {
    const q = new URLSearchParams(params.toString());
    q.set("run", id);
    if (org) q.set("org", org);
    router.replace(`/workbench?${q.toString()}`);
    setSel({ kind: "verification" });
  };
  const start = useMutation({
    mutationFn: (slug: string) => api<WorkflowRunDetail>(`${orgPath(org!)}/workflows/${slug}/runs`, { method: "POST" }),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["runs", org] });
      setRun(r.id);
    },
  });

  if (me.isLoading || workflows.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  if (!org) return <Notice tone="info">You have no workspace yet. <Link className="underline" href="/onboarding">Get started</Link>.</Notice>;
  if (workflows.data && workflows.data.length === 0)
    return (
      <div className="max-w-xl space-y-4">
        <div className="rounded-md border border-line bg-panel">
          <Observers org={org} devices={devices.data ?? []} />
        </div>
      <Notice tone="info">
        No workflow in this workspace yet. Create one on <Link className="underline" href={`/workflows?org=${org}`}>Workflows</Link> or follow{" "}
        <Link className="underline" href="/onboarding">Get started</Link>.
      </Notice>
      </div>
    );

  return (
    <div className="-mx-4 -my-5 flex h-[calc(100vh-44px)] min-h-[600px] flex-col md:-mx-7">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5 md:px-7">
        <h1 className="text-[15px] font-semibold">Workbench</h1>
        <label className="flex items-center gap-2 text-[12px] text-muted">
          Workflow
          <select className="field py-1" value={wf?.slug ?? ""} onChange={(e) => setWfSlug(e.target.value)}>
            {workflows.data?.map((w) => (
              <option key={w.slug} value={w.slug}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        {role !== "viewer" && wf && (
          <button className="btn btn-primary" disabled={start.isPending} onClick={() => start.mutate(wf.slug)}>
            <Play size={13} aria-hidden /> Run workflow
          </button>
        )}
        {start.error && <span className="text-[13px] text-bad">{start.error.message}</span>}
        <div className="ml-auto flex items-center gap-3">
          <Link className="text-[12px] text-accent hover:underline" href={`/twin?org=${org}`}>
            Digital twin
          </Link>
          <OrgSelect orgs={orgs} org={org} select={select} />
        </div>
      </div>
      <Split
        side="bottom"
        label="Resize the timeline"
        initial={170}
        min={90}
        max={360}
        className="flex-1"
        pane={<Timeline run={run.data} sel={sel} onSelect={setSel} />}
      >
        <Split
          side="start"
          label="Resize the instruments panel"
          initial={260}
          min={200}
          max={420}
          className="h-full"
          pane={<Instruments org={org} devices={devices.data ?? []} workflow={wf} runs={runs.data ?? []} runId={runId} onRun={setRun} />}
        >
          <Split
            side="end"
            label="Resize the inspector"
            initial={340}
            min={260}
            max={560}
            className="h-full"
            pane={<Inspector run={run.data} sel={sel} />}
          >
            <RunView run={run.data} loading={run.isLoading} error={run.error?.message} sel={sel} onSelect={setSel} />
          </Split>
        </Split>
      </Split>
    </div>
  );
}

// ----------------------------------------------------------------------------------------------- left: instruments

function Instruments({
  org,
  devices,
  workflow,
  runs,
  runId,
  onRun,
}: {
  org: string;
  devices: Device[];
  workflow: Workflow | undefined;
  runs: { id: string; workflow: string; state: string; verdict?: string | null; created_at: string }[];
  runId: string | null;
  onRun: (id: string) => void;
}) {
  const used = useMemo(() => {
    const keys = new Set(((workflow?.definition as { steps?: { device: string }[] })?.steps ?? []).map((s) => s.device));
    return devices.filter((d) => d.environment === workflow?.environment && keys.has(d.key));
  }, [devices, workflow]);
  const numeric = used.flatMap((d) =>
    d.capabilities
      .filter((c) => c.kind === "property" && c.data_schema?.type === "number")
      .map((c) => ({ device: d, name: c.name, title: c.title })),
  );
  const reads = useQueries({
    queries: numeric.map((n) => ({
      queryKey: ["prop", org, n.device.id, n.name],
      queryFn: () => api<PropertyRead>(`${orgPath(org)}/devices/${n.device.id}/properties/${n.name}`),
      refetchInterval: 1500,
    })),
  });
  return (
    <div className="flex h-full flex-col">
      <section aria-labelledby="instruments-h" className="border-b border-line p-3">
        <h2 id="instruments-h" className="mb-2 text-[12px] font-medium text-faint">
          Instruments {workflow && <span className="num">· {workflow.environment}</span>}
        </h2>
        {used.length === 0 && <p className="text-[12px] text-muted">The workflow uses no discovered device.</p>}
        <ul className="space-y-2.5">
          {used.map((d) => (
            <li key={d.id}>
              <div className="flex items-center gap-2 text-[13px]">
                <span aria-hidden className={clsx("size-1.5 rounded-full", d.present ? "bg-ok" : "bg-faint")} />
                <span className="font-medium">{d.key}</span>
                <KindBadge kind={d.environment_kind} />
              </div>
              <dl className="mt-1 grid grid-cols-[1fr_auto] gap-x-2 pl-3.5 text-[12px]">
                {numeric.map((n, i) =>
                  n.device.id === d.id ? (
                    <div key={n.name} className="contents">
                      <dt className="num truncate text-muted" title={n.title}>
                        {n.name}
                      </dt>
                      <dd className="num text-right">{reads[i]?.data ? String(reads[i]!.data!.value) : reads[i]?.error ? "unreachable" : "…"}</dd>
                    </div>
                  ) : null,
                )}
              </dl>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-faint">Read live from the devices every 1.5 s.</p>
      </section>
      <Observers org={org} devices={devices} />
      <section aria-labelledby="runs-h" className="min-h-0 flex-1 overflow-auto p-3">
        <h2 id="runs-h" className="mb-2 text-[12px] font-medium text-faint">
          Runs
        </h2>
        {runs.length === 0 && <p className="text-[12px] text-muted">No run yet.</p>}
        <ul className="space-y-px">
          {runs.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => onRun(r.id)}
                aria-current={r.id === runId ? "true" : undefined}
                className={clsx(
                  "flex w-full items-center gap-2 rounded-[5px] px-2 py-1.5 text-left text-[12px] transition-colors duration-[80ms]",
                  r.id === runId ? "bg-selected text-ink" : "text-muted hover:bg-hover hover:text-ink",
                )}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{r.workflow}</span>
                  <span className="num block whitespace-nowrap text-[11px] text-muted">{timestamp(r.created_at)}</span>
                </span>
                <span className="shrink-0">{r.verdict ? <VerdictBadge verdict={r.verdict} /> : <Badge tone={stateTone(r.state)}>{RUN_STATE[r.state] ?? r.state}</Badge>}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

// --------------------------------------------------------------------------------------------- centre: the run

function RunView({
  run,
  loading,
  error,
  sel,
  onSelect,
}: {
  run: WorkflowRunDetail | undefined;
  loading: boolean;
  error?: string;
  sel: Selection;
  onSelect: (s: Selection) => void;
}) {
  if (loading) return <p className="p-4 text-[13px] text-muted">Loading the run…</p>;
  if (error) return <div className="p-4"><Notice tone="bad">{error}</Notice></div>;
  if (!run) return <p className="p-4 text-[13px] text-muted">Select a workflow and run it. Its steps and result appear here.</p>;
  const reported = run.reported as { value?: string; device?: string; output?: Record<string, unknown> } | null;
  const verification = run.verification as { report?: { conditions?: { name?: string; result: string; observed: unknown[] }[] } } | null;
  const cond = verification?.report?.conditions?.[0];
  const busy = run.state === "queued" || run.state === "running";
  return (
    <div className="p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-[14px] font-semibold">{run.workflow_name}</h2>
        <span className="num text-[12px] text-faint">run {run.id.slice(0, 8)}</span>
        <Badge tone={stateTone(run.state)}>{RUN_STATE[run.state] ?? run.state}</Badge>
        <Badge tone="warn">SIMULATED EVIDENCE</Badge>
        {busy && <span role="status" className="text-[12px] text-muted">The worker is executing; this view updates by itself.</span>}
      </div>
      {run.error && run.state !== "succeeded" && (
        <div className="mb-3">
          <Notice tone={run.state === "outcome_unknown" ? "warn" : "bad"}>
            <span className="num">{String(run.error.code)}</span>: {String(run.error.message)}
          </Notice>
        </div>
      )}
      <div className="mb-4 grid gap-3 lg:grid-cols-2">
        <section aria-labelledby="reported-h" className="rounded-md border border-line p-3">
          <h3 id="reported-h" className="mb-1 text-[12px] font-medium text-faint">
            Reported by the instrument
          </h3>
          {reported ? (
            <>
              <div className="flex items-center gap-2">
                <Badge tone={reported.value === "succeeded" ? "ok" : "bad"}>{reported.value}</Badge>
                <span className="num text-[12px] text-muted">{reported.device}</span>
              </div>
              {reported.output && (
                <div className="num mt-2 text-[12px] text-muted">
                  {Object.entries(reported.output)
                    .filter(([k]) => k !== "request_id")
                    .map(([k, v]) => (
                      <div key={k}>
                        {k} = {String(v)}
                      </div>
                    ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-[13px] text-muted">{busy ? "Waiting for the instrument…" : "No report."}</p>
          )}
        </section>
        <section aria-labelledby="verified-h" className="rounded-md border border-line p-3">
          <h3 id="verified-h" className="mb-1 text-[12px] font-medium text-faint">
            Independently verified (OpenMHS engine)
          </h3>
          {run.verdict ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <VerdictBadge verdict={run.verdict} />
                {run.outcome_class && <ClassBadge value={run.outcome_class} />}
              </div>
              {cond && (
                <button type="button" className="mt-2 block text-left text-[12px] text-muted hover:text-ink" onClick={() => onSelect({ kind: "verification" })}>
                  {cond.name} · observed <span className="num text-ink">{observedText(cond.observed)}</span> · {CONDITION_RESULT[cond.result] ?? cond.result}
                </button>
              )}
            </>
          ) : (
            <p className="text-[13px] text-muted">{busy ? "Verified after the last step." : "Not verified."}</p>
          )}
        </section>
      </div>
      <h3 className="mb-1 text-[13px] font-medium">Steps</h3>
      <ol className="divide-y divide-line rounded-md border border-line">
        {run.steps.map((s) => (
          <li key={s.position}>
            <button
              type="button"
              onClick={() => onSelect({ kind: "step", position: s.position })}
              aria-current={sel.kind === "step" && sel.position === s.position ? "true" : undefined}
              className={clsx(
                "flex w-full items-center gap-3 px-3 py-2 text-left text-[13px]",
                sel.kind === "step" && sel.position === s.position ? "bg-sunken" : "hover:bg-sunken",
              )}
            >
              <span className="num w-5 text-faint">{s.position + 1}</span>
              <span className="num">
                {s.device}.{s.action}
              </span>
              <span className="num truncate text-[12px] text-muted">{Object.keys(s.input).length ? JSON.stringify(s.input) : ""}</span>
              <span className="ml-auto flex items-center gap-2">
                {s.dispatches > 1 && <Badge tone="neutral">sent {s.dispatches}×</Badge>}
                <Badge tone={stateTone(s.state)}>{RUN_STATE[s.state] ?? s.state}</Badge>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

// ------------------------------------------------------------------------------------------ right: the inspector

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </>
  );
}

function Inspector({ run, sel }: { run: WorkflowRunDetail | undefined; sel: Selection }) {
  if (!run) return <p className="p-4 text-[13px] text-muted">Nothing selected.</p>;
  if (sel.kind === "step") {
    const s = run.steps.find((x) => x.position === sel.position);
    return s ? <StepInspector step={s} /> : null;
  }
  const v = run.verification as {
    verdict?: string;
    report?: { conditions?: { name?: string; op: string; result: string; observed: unknown[]; evidence: string }[]; reasons?: { code: string; detail?: string }[] };
    contract?: { contract?: string; version?: string };
  } | null;
  const p = run.provenance as { engine?: { version?: string; commit?: string; binary_sha256?: string }; contract_sha256?: string; evidence_sha256?: string } | null;
  return (
    <div className="p-4">
      <h2 className="mb-3 text-[13px] font-semibold">Verification</h2>
      {!v ? (
        <p className="text-[13px] text-muted">The engine verifies the run after its last step.</p>
      ) : (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1.5 text-[12px]">
          <Field label="Verdict">
            <VerdictBadge verdict={v.verdict} />
          </Field>
          <Field label="Contract">
            <span className="num">
              {v.contract?.contract} v{v.contract?.version}
            </span>
          </Field>
          {v.report?.conditions?.map((c, i) => (
            <Field key={i} label={`Condition ${i + 1}`}>
              <div>{c.name}</div>
              <div className="num text-muted">
                {c.evidence} {c.op}: {CONDITION_RESULT[c.result] ?? c.result}, observed {observedText(c.observed)}
              </div>
            </Field>
          ))}
          {v.report?.reasons && v.report.reasons.length > 0 && (
            <Field label="Reasons">
              {v.report.reasons.map((r, i) => (
                <div key={i} className="num">
                  {r.code}
                  {r.detail ? `: ${r.detail}` : ""}
                </div>
              ))}
            </Field>
          )}
          {p?.engine && (
            <Field label="Engine">
              <span className="num">
                {p.engine.version} · {p.engine.commit?.slice(0, 9)} · {shortDigest(p.engine.binary_sha256)}
              </span>
            </Field>
          )}
          {p?.contract_sha256 && (
            <Field label="Digests">
              <div className="num">contract {shortDigest(p.contract_sha256)}</div>
              <div className="num">evidence {shortDigest(p.evidence_sha256)}</div>
            </Field>
          )}
        </dl>
      )}
    </div>
  );
}

function StepInspector({ step }: { step: WorkflowStep }) {
  const ms = step.started_at && step.finished_at ? new Date(step.finished_at).getTime() - new Date(step.started_at).getTime() : null;
  return (
    <div className="p-4">
      <h2 className="mb-3 text-[13px] font-semibold">
        Step {step.position + 1}: <span className="num">{step.device}.{step.action}</span>
      </h2>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1.5 text-[12px]">
        <Field label="State">
          <Badge tone={stateTone(step.state)}>{RUN_STATE[step.state] ?? step.state}</Badge>
        </Field>
        <Field label="Request">
          <pre className="num whitespace-pre-wrap">{JSON.stringify(step.input, null, 1)}</pre>
        </Field>
        <Field label="Request id">
          <span className="num">{step.request_id}</span>
        </Field>
        <Field label="Repeat-safe">
          {step.idempotent ? "Yes: the device ignores a repeated request id" : "No: never re-sent after a crash"}
        </Field>
        <Field label="Sent">
          <span className="num">{step.dispatches}×</span>
        </Field>
        <Field label="Device answer">
          <pre className="num whitespace-pre-wrap">{step.output === null || step.output === undefined ? "—" : JSON.stringify(step.output, null, 1)}</pre>
        </Field>
        {step.error && (
          <Field label="Error">
            <span className="text-bad">{step.error}</span>
          </Field>
        )}
        <Field label="Started">
          <Time iso={step.started_at} />
        </Field>
        <Field label="Duration">
          <span className="num">{ms === null ? "—" : `${ms} ms`}</span>
        </Field>
        <Field label="Invocation">
          <span className="num">{step.invocation_id ?? "—"}</span>
        </Field>
      </dl>
    </div>
  );
}

// ------------------------------------------------------------------------------------------- bottom: timeline

function Timeline({ run, sel, onSelect }: { run: WorkflowRunDetail | undefined; sel: Selection; onSelect: (s: Selection) => void }) {
  const [now, setNow] = useState(() => Date.now());
  const busy = run && (run.state === "queued" || run.state === "running");
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [busy]);
  if (!run) return <p className="p-3 text-[12px] text-muted">The run timeline appears here.</p>;
  const timed = run.steps.filter((s) => s.started_at);
  if (timed.length === 0) return <p className="p-3 text-[12px] text-muted">No step has started yet.</p>;
  const t0 = Math.min(...timed.map((s) => new Date(s.started_at!).getTime()));
  const end = (s: WorkflowStep) => (s.finished_at ? new Date(s.finished_at).getTime() : now);
  const t1 = Math.max(...timed.map(end), t0 + 1);
  const span = t1 - t0;
  const W = 1000;
  const rowH = 20;
  return (
    <div className="p-3">
      <h2 className="mb-1.5 text-[12px] font-medium text-faint">
        Timeline <span className="num">· {(span / 1000).toFixed(2)} s · worker clock</span>
      </h2>
      <svg viewBox={`0 0 ${W} ${run.steps.length * rowH + 4}`} className="w-full" role="img" aria-label="Step timeline">
        {run.steps.map((s, i) => {
          if (!s.started_at) return null;
          const x = ((new Date(s.started_at).getTime() - t0) / span) * (W - 200) + 190;
          const w = Math.max(2, ((end(s) - new Date(s.started_at).getTime()) / span) * (W - 200));
          const on = sel.kind === "step" && sel.position === s.position;
          const fill = s.state === "completed" ? "var(--color-ok)" : s.state === "failed" || s.state === "refused" ? "var(--color-bad)" : s.state === "outcome_unknown" ? "var(--color-warn)" : "var(--color-accent)";
          return (
            <g key={s.position} onClick={() => onSelect({ kind: "step", position: s.position })} className="cursor-pointer">
              <text x={0} y={i * rowH + 14} fontSize="12" fill={on ? "var(--color-ink)" : "var(--color-muted)"} fontFamily="var(--font-mono)">
                {s.position + 1} {s.device}.{s.action}
              </text>
              <rect x={x} y={i * rowH + 4} width={w} height={rowH - 8} rx={2} fill={fill} opacity={on ? 1 : 0.75} />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ----------------------------------------------------------------------------------------- left: observed robots

type ObserverSummary = {
  topics?: number;
  nodes?: number;
  topics_by_state?: Record<string, number>;
  required_expected_problems?: string[];
  clock_state?: string;
};

/** Environments whose devices only observe (a `summary` property and no action): a robot graph seen read-only. */
function Observers({ org, devices }: { org: string; devices: Device[] }) {
  const observers = devices.filter(
    (d) =>
      d.present &&
      d.capabilities.some((c) => c.kind === "property" && c.name === "summary") &&
      !d.capabilities.some((c) => c.kind === "action"),
  );
  const reads = useQueries({
    queries: observers.map((d) => ({
      queryKey: ["observer-summary", org, d.id],
      queryFn: () => api<PropertyRead>(`${orgPath(org)}/devices/${d.id}/properties/summary`),
      refetchInterval: 1500,
    })),
  });
  if (observers.length === 0) return null;
  return (
    <section aria-labelledby="observers-h" className="border-b border-line p-3">
      <h2 id="observers-h" className="mb-2 text-[12px] font-medium text-faint">
        Observed robots
      </h2>
      <ul className="space-y-3">
        {observers.map((d, i) => {
          const q = reads[i];
          const v = (q?.data?.value ?? {}) as ObserverSummary;
          const problems = v.required_expected_problems ?? [];
          return (
            <li key={d.id}>
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="font-medium">{d.environment}</span>
                <KindBadge kind={d.environment_kind} />
              </div>
              {q?.error ? (
                <p className="mt-1 text-[12px] text-bad">unreachable: {q.error.message}</p>
              ) : (
                <>
                  <p className="num mt-1 text-[12px] text-muted">
                    {v.nodes ?? "…"} nodes · {v.topics ?? "…"} topics · clock {v.clock_state ?? "…"}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {Object.entries(v.topics_by_state ?? {}).map(([state, n]) => (
                      <span key={state} className="inline-flex items-center gap-1 text-[12px]">
                        <ObsState value={state} />
                        <span className="num text-muted">{n}</span>
                      </span>
                    ))}
                  </div>
                  {problems.length > 0 ? (
                    <p className="mt-1 text-[12px] text-bad" role="status">
                      Required but not healthy: <span className="num">{problems.join(", ")}</span>
                    </p>
                  ) : (
                    q?.data && <p className="mt-1 text-[12px] text-faint">Every required topic is publishing.</p>
                  )}
                </>
              )}
              <Link className="mt-1 inline-block text-[12px] text-accent hover:underline" href={`/hardware?org=${org}`}>
                Inspect in the Hardware Hub
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
