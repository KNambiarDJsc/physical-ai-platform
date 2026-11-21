"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { api, orgPath, type Workflow, type WorkflowRunDetail } from "@/lib/api/client";
import { Notice, PageHeader } from "./AppShell";
import { KindBadge, useCatalog, useDiscover } from "./Hardware";
import { RequireIdentity } from "./Identity";
import { Badge, ClassBadge } from "./ui";
import { VerdictBadge } from "./Workbench";
import { TemplateForm } from "./Workflows";
import { OrgSelect, RUN_STATE, useDevices, useEnvironments, useOrg, useRuns, useWorkflows } from "./Workspace";

export function OnboardingView() {
  return (
    <RequireIdentity>
      <Onboarding />
    </RequireIdentity>
  );
}

function Step({
  n,
  title,
  done,
  active,
  open = active,
  children,
}: {
  n: number;
  title: string;
  done: boolean;
  active: boolean;
  open?: boolean;
  children?: ReactNode;
}) {
  return (
    <li className={clsx("rounded-md border bg-panel", active ? "border-accent/60" : "border-line")}>
      <div className="flex items-center gap-3 px-4 py-3">
        <span
          aria-hidden
          className={clsx(
            "grid size-6 shrink-0 place-items-center rounded-full border text-[12px] font-medium",
            done ? "border-ok bg-ok-soft text-ok" : active ? "border-accent text-accent" : "border-line text-faint",
          )}
        >
          {done ? <Check size={13} /> : n}
        </span>
        <h2 className={clsx("text-[13.5px] font-medium", !done && !active && "text-muted")}>{title}</h2>
        {done && <span className="ml-auto text-[12px] text-ok">Done</span>}
      </div>
      {open && children && <div className="border-t border-line px-4 py-4">{children}</div>}
    </li>
  );
}

function Onboarding() {
  const { me, orgs, org, role, select } = useOrg();
  const envs = useEnvironments(org);
  const devices = useDevices(org);
  const workflows = useWorkflows(org);
  const runs = useRuns(org);
  if (me.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  const hasOrg = !!org;
  const hasEnv = (envs.data ?? []).length > 0;
  const hasDevices = (devices.data ?? []).some((d) => d.present);
  const hasWorkflow = (workflows.data ?? []).length > 0;
  const verified = (runs.data ?? []).some((r) => !!r.verdict);
  const steps = [hasOrg, hasEnv, hasDevices, hasWorkflow, verified];
  const active = steps.findIndex((s) => !s);
  return (
    <>
      <PageHeader
        title="Get started"
        subtitle="Connect a simulated instrument, discover what it can do, run a workflow and receive a result the engine verified."
        actions={<OrgSelect orgs={orgs} org={org} select={select} />}
      />
      <ol className="max-w-4xl space-y-2">
        <Step n={1} title="Create a workspace" done={hasOrg} active={active === 0}>
          <NewWorkspace />
        </Step>
        <Step n={2} title="Connect an environment" done={hasEnv} active={active === 1}>
          {org && (role === "admin" ? <ConnectEnvironment org={org} /> : <Notice tone="info">An admin of {org} connects environments.</Notice>)}
        </Step>
        <Step n={3} title="Discover its devices and their capabilities" done={hasDevices} active={active === 2}>
          {org && <Discover org={org} envSlugs={(envs.data ?? []).map((e) => e.slug)} canDiscover={role !== "viewer"} />}
        </Step>
        <Step n={4} title="Create a workflow" done={hasWorkflow} active={active === 3}>
          {org && <TemplateForm org={org} />}
        </Step>
        <Step n={5} title="Run it and read the verified result" done={verified} active={active === 4} open={active === 4 || verified}>
          {org && workflows.data?.[0] && <FirstRun org={org} workflow={workflows.data[0]} />}
        </Step>
      </ol>
      {active === -1 && org && (
        <div className="mt-4 max-w-4xl">
          <Notice tone="info">
            Every step is done. Continue in the <Link className="font-medium underline" href={`/workbench?org=${org}`}>Workbench</Link>, inspect devices
            in the <Link className="underline" href={`/hardware?org=${org}`}>Hardware Hub</Link>, or compare releases from{" "}
            <Link className="underline" href="/">Overview</Link>.
          </Notice>
        </div>
      )}
    </>
  );
}

function NewWorkspace() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const create = useMutation({
    mutationFn: () => api("/api/v1/orgs", { method: "POST", body: JSON.stringify({ slug, name }) }),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <label className="text-[13px]">
        <span className="mb-1 block text-muted">Workspace name</span>
        <input
          className="field w-56"
          value={name}
          required
          onChange={(e) => {
            setName(e.target.value);
            if (!slug || slug === toSlug(name)) setSlug(toSlug(e.target.value));
          }}
        />
      </label>
      <label className="text-[13px]">
        <span className="mb-1 block text-muted">Workspace slug</span>
        <input className="field num w-44" value={slug} required pattern="[a-z0-9][a-z0-9\-]{0,62}" onChange={(e) => setSlug(e.target.value)} />
      </label>
      <button className="btn btn-primary" type="submit" disabled={create.isPending}>
        Create workspace
      </button>
      {create.error && <Notice tone="bad">{create.error.message}</Notice>}
      <p className="w-full text-[12px] text-faint">You become its admin. A workspace is an organization: projects, environments and workflows belong to it.</p>
    </form>
  );
}

const toSlug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);

function ConnectEnvironment({ org }: { org: string }) {
  const qc = useQueryClient();
  const catalog = useCatalog();
  const [choice, setChoice] = useState<string | null>(null);
  const connect = useMutation({
    mutationFn: (key: string) => api(`${orgPath(org)}/environments`, { method: "POST", body: JSON.stringify({ config_key: key }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["environments", org] }),
  });
  if (catalog.isLoading) return <p className="text-[13px] text-muted">Loading the environments this installation offers…</p>;
  const entries = catalog.data ?? [];
  if (entries.length === 0) return <Notice tone="warn">This installation offers no environment. The operator sets PAP_ENVIRONMENTS.</Notice>;
  const picked = choice ?? entries[0]!.key;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        connect.mutate(picked);
      }}
    >
      <fieldset>
        <legend className="mb-2 text-[13px] text-muted">Environments offered by this installation</legend>
        <div className="space-y-1.5">
          {entries.map((c) => (
            <label key={c.key} className={clsx("flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2", picked === c.key ? "border-accent/60 bg-sunken" : "border-line")}>
              <input type="radio" name="environment" className="mt-1" checked={picked === c.key} onChange={() => setChoice(c.key)} />
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="font-medium">{c.name}</span>
                  <KindBadge kind={c.kind} />
                  <span className="num text-[12px] text-faint">{c.adapter} · {c.endpoint}</span>
                </span>
                {c.description && <span className="mt-0.5 block text-[12px] text-muted">{c.description}</span>}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <button className="btn btn-primary mt-3" type="submit" disabled={connect.isPending}>
        Connect environment
      </button>
      {connect.error && <div className="mt-2"><Notice tone="bad">{connect.error.message}</Notice></div>}
    </form>
  );
}

function Discover({ org, envSlugs, canDiscover }: { org: string; envSlugs: string[]; canDiscover: boolean }) {
  const discover = useDiscover(org);
  const env = envSlugs[0];
  if (!env) return null;
  return (
    <div>
      <p className="mb-3 text-[13px] text-muted">
        The platform reads each device&apos;s W3C Thing Description: its properties, its actions and their inputs. Discovery reads only; it sends no command.
      </p>
      {canDiscover ? (
        <button className="btn btn-primary" onClick={() => discover.mutate(env)} disabled={discover.isPending}>
          {discover.isPending ? "Discovering…" : `Discover devices in ${env}`}
        </button>
      ) : (
        <Notice tone="info">An engineer or admin runs discovery.</Notice>
      )}
      {discover.error && <div className="mt-2"><Notice tone="bad">{discover.error.message}</Notice></div>}
    </div>
  );
}

function FirstRun({ org, workflow }: { org: string; workflow: Workflow }) {
  const qc = useQueryClient();
  const [runId, setRunId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: () => api<WorkflowRunDetail>(`${orgPath(org)}/workflows/${workflow.slug}/runs`, { method: "POST" }),
    onSuccess: (r) => setRunId(r.id),
  });
  const run = useQuery({
    queryKey: ["run", org, runId],
    queryFn: () => api<WorkflowRunDetail>(`${orgPath(org)}/workflow-runs/${runId}`),
    enabled: !!runId,
    refetchInterval: (q) => {
      const s = q.state.data?.state;
      if (s && !["queued", "running"].includes(s)) {
        void qc.invalidateQueries({ queryKey: ["runs", org] });
        return false;
      }
      return 700;
    },
  });
  const r = run.data;
  return (
    <div>
      <p className="mb-3 text-[13px] text-muted">
        The worker sends each step to the instrument, journalling it before and after. Then the OpenMHS engine checks the pump&apos;s claim against the
        balance&apos;s measurement.
      </p>
      <button className="btn btn-primary" onClick={() => start.mutate()} disabled={start.isPending || (r && ["queued", "running"].includes(r.state))}>
        Run {workflow.name}
      </button>
      {start.error && <div className="mt-2"><Notice tone="bad">{start.error.message}</Notice></div>}
      {r && (
        <div className="mt-3 rounded-md border border-line p-3 text-[13px]" role="status">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted">Run</span>
            <Badge tone="neutral">{RUN_STATE[r.state] ?? r.state}</Badge>
            {r.steps.map((s) => (
              <span key={s.position} className="num text-[12px] text-muted">
                {s.device}.{s.action}: {RUN_STATE[s.state] ?? s.state}
              </span>
            ))}
          </div>
          {r.verdict && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-muted">Reported</span>
              <Badge tone={(r.reported as { value?: string })?.value === "succeeded" ? "ok" : "bad"}>
                {String((r.reported as { value?: string })?.value)}
              </Badge>
              <span className="text-muted">Verified by the engine</span>
              <VerdictBadge verdict={r.verdict} />
              {r.outcome_class && <ClassBadge value={r.outcome_class} />}
              <Link className="ml-auto text-accent underline" href={`/workbench?org=${org}&run=${r.id}`}>
                Open in the Workbench
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
