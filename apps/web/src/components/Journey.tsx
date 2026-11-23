"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { api, orgPath, type Proposal, type Workflow } from "@/lib/api/client";
import { Notice, PageHeader } from "./AppShell";
import { RequireIdentity } from "./Identity";
import { Badge, Time } from "./ui";
import { ReportButtons, VerdictBadge } from "./Workbench";
import { OrgSelect, useDevices, useOrg, useRuns, useWorkflows } from "./Workspace";

export function JourneyView() {
  return (
    <RequireIdentity>
      <Journey />
    </RequireIdentity>
  );
}

function Step({ n, title, done, active, children }: { n: number; title: string; done: boolean; active: boolean; children: ReactNode }) {
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
      <div className="border-t border-line px-4 py-3 text-[13px]">{children}</div>
    </li>
  );
}

type Params = { volume_ul?: number; tolerance_pct?: number; fault?: string };

function Journey() {
  const { me, orgs, org, role, select } = useOrg();
  const qc = useQueryClient();
  const devices = useDevices(org);
  const workflows = useWorkflows(org);
  const runs = useRuns(org);
  const proposals = useQuery({
    queryKey: ["proposals", org],
    queryFn: () => api<Proposal[]>(`${orgPath(org!)}/experiment-proposals`),
    enabled: !!org,
    refetchInterval: 4000,
  });
  const sessions = useQuery({
    queryKey: ["agent-sessions", org],
    queryFn: () => api<{ id: string }[]>(`${orgPath(org!)}/agent/sessions`),
    enabled: !!org,
  });
  const [workflow, setWorkflow] = useState("");
  const [why, setWhy] = useState("");
  const request = useMutation({
    mutationFn: () =>
      api<Proposal>(`${orgPath(org!)}/experiment-proposals`, { method: "POST", body: JSON.stringify({ workflow, rationale: why.trim() }) }),
    onSuccess: () => {
      setWhy("");
      void qc.invalidateQueries({ queryKey: ["proposals", org] });
    },
  });

  if (me.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  if (!org) return <Notice tone="info">You have no workspace yet. Start on the <Link className="underline" href="/onboarding">Get started</Link> page.</Notice>;

  const devs = devices.data ?? [];
  const find = (key: string) => devs.find((d) => d.key === key);
  const [pump, balance, control] = [find("pump"), find("balance"), find("simulation")];
  const discovered = !!pump && !!balance;
  const wfs = workflows.data ?? [];
  const normal = wfs.filter((w) => w.template === "dispense-and-verify");
  const faulty = wfs.filter((w) => w.template === "dispense-with-fault");
  const configured = normal.length > 0 && faulty.length > 0;
  const lab = [...normal, ...faulty];
  const props = proposals.data ?? [];
  const approved = props.filter((p) => p.state === "approved").length;
  const allRuns = runs.data ?? [];
  const success = allRuns.find((r) => r.verdict === "SATISFIED");
  const failing = allRuns.find((r) => r.verdict === "VIOLATED");
  const investigated = (sessions.data ?? []).length > 0;
  const steps = [discovered, configured, approved > 0, !!success && !!failing, investigated];
  const active = steps.findIndex((d) => !d);
  const isActive = (i: number) => (active === -1 ? false : active === i);
  const ask = failing
    ? `Investigate workflow run ${failing.id}. The pump reported a result; what did the independent measurement show, what is the evidence, and what follow-up experiment would you draft? Cite ids.`
    : "";

  return (
    <>
      <PageHeader
        title="Laboratory experiment"
        subtitle="One guided path from a simulated dispensing procedure to evidence you can export. Each step opens the page where the work happens; its status comes from stored data."
        actions={<OrgSelect orgs={orgs} org={org} select={select} />}
      />
      <Notice tone="info">Everything here runs on a simulated bench: no physical hardware is involved, and every result is labelled simulated.</Notice>
      <ol className="mt-4 max-w-4xl space-y-3">
        <Step n={1} title="Discover the instruments" done={steps[0]!} active={isActive(0)}>
          {devices.isLoading && <p className="text-muted">Loading…</p>}
          {devices.error && <Notice tone="bad">{devices.error.message}</Notice>}
          {discovered ? (
            <p className="flex flex-wrap items-center gap-2">
              {[pump, balance, control].filter(Boolean).map((d) => (
                <span key={d!.id} className="flex items-center gap-1">
                  <span className="num">{d!.key}</span>
                  {d!.declares_simulated && <Badge tone="warn">SIMULATED</Badge>}
                </span>
              ))}
              <Link className="ml-2 text-accent underline" href={`/hardware?org=${org}`}>Inspect capabilities in the Hardware Hub</Link>
            </p>
          ) : (
            !devices.isLoading && (
              <p className="text-muted">
                No pump and balance found yet. Connect the virtual laboratory on <Link className="text-accent underline" href="/onboarding">Get started</Link>.
              </p>
            )
          )}
        </Step>

        <Step n={2} title="Configure the procedure and its tolerance" done={steps[1]!} active={isActive(1)}>
          {lab.length === 0 && <p className="text-muted">No dispensing workflow yet. Create one from a template in Workflows: a normal bench, and one with a simulated fault.</p>}
          {lab.length > 0 && (
            <ul className="space-y-1">
              {lab.map((w: Workflow) => {
                const p = (w.parameters ?? {}) as Params;
                return (
                  <li key={w.id} className="flex flex-wrap items-center gap-2">
                    <span className="num">{w.slug}</span>
                    <span className="text-muted">
                      {p.volume_ul ?? 50} µL, accepted within ±{p.tolerance_pct ?? 2} %
                    </span>
                    {w.template === "dispense-with-fault" ? <Badge tone="warn">simulated fault: {String(p.fault ?? "partial_blockage").replace(/_/g, " ")}</Badge> : <Badge tone="neutral">normal bench</Badge>}
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-2 text-[12px] text-muted">
            The tolerance is part of the procedure&apos;s contract. A result outside it is a contract violation; the OpenMHS engine decides, not this page.{" "}
            <Link className="text-accent underline" href={`/workflows?org=${org}`}>Create or change workflows</Link>
          </p>
        </Step>

        <Step n={3} title="Request a run and have it approved by someone else" done={steps[2]!} active={isActive(2)}>
          <p className="mb-2 text-muted">Anyone in the workspace can ask for a run. A different engineer approves it in Workflows: nobody approves their own request.</p>
          {lab.length > 0 && (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (workflow && why.trim().length >= 10) request.mutate();
              }}
            >
              <label className="text-[12px] text-muted" htmlFor="j-workflow">
                Procedure
                <select id="j-workflow" className="field mt-1 block" value={workflow} onChange={(e) => setWorkflow(e.target.value)}>
                  <option value="">Choose…</option>
                  {lab.map((w) => (
                    <option key={w.id} value={w.slug}>{w.slug}</option>
                  ))}
                </select>
              </label>
              <label className="min-w-[16rem] flex-1 text-[12px] text-muted" htmlFor="j-why">
                Why run it (at least 10 characters)
                <input id="j-why" className="field mt-1 block w-full" value={why} maxLength={500} onChange={(e) => setWhy(e.target.value)} />
              </label>
              <button className="btn btn-primary" disabled={!workflow || why.trim().length < 10 || request.isPending}>
                {request.isPending ? "Sending…" : "Request run"}
              </button>
              {request.error && <span role="alert" className="text-[12px] text-bad">{request.error.message}</span>}
            </form>
          )}
          {props.length > 0 && (
            <ul className="mt-3 space-y-1">
              {props.slice(0, 5).map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-2">
                  <Badge tone={p.state === "approved" ? "ok" : p.state === "rejected" ? "neutral" : "warn"}>{p.state === "proposed" ? "awaiting approval" : p.state}</Badge>
                  <span className="num">{p.workflow}</span>
                  <span className="text-muted">asked by {p.proposed_by.split("|").pop()}</span>
                  {p.decided_by && <span className="text-muted">· decided by {p.decided_by.split("|").pop()}</span>}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[12px]">
            <Link className="text-accent underline" href={`/workflows?org=${org}`}>Approve or reject in Workflows</Link>
            {role === "viewer" && <span className="text-muted"> (engineers decide)</span>}
          </p>
        </Step>

        <Step n={4} title="Inspect the runs" done={steps[3]!} active={isActive(3)}>
          <ul className="space-y-1">
            {[
              ["Successful run", success],
              ["Failing run", failing],
            ].map(([label, r]) => (
              <li key={String(label)} className="flex flex-wrap items-center gap-2">
                <span className="w-28 text-muted">{String(label)}</span>
                {r && typeof r === "object" ? (
                  <>
                    <VerdictBadge verdict={r.verdict ?? ""} />
                    <Link className="text-accent underline" href={`/workbench?org=${org}&run=${r.id}`}>{r.workflow_name}</Link>
                    <Time iso={r.created_at} />
                  </>
                ) : (
                  <span className="text-muted">none yet: it appears after an approved run finishes</span>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[12px] text-muted">The pump reports what it was told to deliver. The balance measures what arrived. The engine compares the measurement with the tolerance.</p>
        </Step>

        <Step n={5} title="Investigate the failure with the agent" done={steps[4]!} active={isActive(4)}>
          <p className="text-muted">The agent reads stored evidence only, cites the ids it used, shows its trace and cost, and may draft a follow-up that you decide whether to file.</p>
          {failing ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Link className="btn btn-primary" href={`/agent?org=${org}&q=${encodeURIComponent(ask)}`}>Ask the agent (language model)</Link>
              <Link className="btn" href={`/agent?org=${org}&q=${encodeURIComponent(`Investigate workflow run ${failing.id}.`)}`}>Rule-based investigation (no model)</Link>
              <span className="text-[12px] text-muted">The second is fixed rules over the same stored records. It is not AI inference, and it works without a model.</span>
            </div>
          ) : (
            <p className="mt-2 text-muted">Available once a run has failed its tolerance.</p>
          )}
        </Step>

        <Step n={6} title="Export the evidence" done={false} active={false}>
          {success || failing ? (
            <ul className="space-y-2">
              {[success, failing].filter(Boolean).map((r) => (
                <li key={r!.id} className="flex flex-wrap items-center gap-2">
                  <span className="num">{r!.workflow_name}</span>
                  <VerdictBadge verdict={r!.verdict ?? ""} />
                  <ReportButtons org={org} runId={r!.id} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">Reports appear here once there is a finished run.</p>
          )}
          <p className="mt-2 text-[12px] text-muted">A report is built from stored records only. The same run always produces the same file.</p>
        </Step>
      </ol>
    </>
  );
}
