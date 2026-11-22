"use client";

import { useQuery, useQueries } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";
import { ApiError, api, orgPath, type Project } from "@/lib/api/client";
import { inFlight, type ExperimentOut, type ExperimentRequestDetail, type SimEnv } from "@/lib/experiments";
import { Notice } from "../AppShell";
import { Badge } from "../ui";

// ---------------------------------------------------------------------------------------------------- data

export const useSimEnvs = (org: string | null) =>
  useQuery({ queryKey: ["sim-envs", org], queryFn: () => api<SimEnv[]>(`${orgPath(org!)}/simulation-environments`), enabled: !!org });

export const useExperiments = (org: string | null) =>
  useQuery({
    queryKey: ["experiments", org],
    queryFn: () => api<ExperimentOut[]>(`${orgPath(org!)}/experiments`),
    enabled: !!org,
    // Something waiting on a person or a host changes without the user doing anything here.
    refetchInterval: (q) => (q.state.data?.some((e) => e.requests.some((r) => r.state === "approved" && r.trials_done < r.trials)) ? 2000 : 8000),
  });

export const useRequest = (org: string | null, id: string | null) =>
  useQuery({
    queryKey: ["experiment-request", org, id],
    queryFn: () => api<ExperimentRequestDetail>(`${orgPath(org!)}/experiment-requests/${id}`),
    enabled: !!org && !!id,
    refetchInterval: (q) => (inFlight(q.state.data) ? 1500 : false),
  });

export type ModelChoice = { ref: string; label: string; project: string };

/** Robot model versions the workspace has registered, across its projects (for the Digital twin). */
export function useModels(org: string | null): { models: ModelChoice[]; loading: boolean } {
  const projects = useQuery({ queryKey: ["projects", org], queryFn: () => api<Project[]>(`${orgPath(org!)}/projects`), enabled: !!org });
  const lists = useQueries({
    queries: (projects.data ?? []).map((p) => ({
      queryKey: ["twin-models", org, p.slug],
      queryFn: () => api<{ slug: string; name: string; versions: { number: number }[] }[]>(`${orgPath(org!)}/projects/${p.slug}/twin/models`),
    })),
  });
  const models = lists.flatMap((l, i) => {
    const p = projects.data?.[i];
    return !p ? [] : (l.data ?? []).flatMap((m) => m.versions.map((v) => ({ ref: `${p.slug}/${m.slug}@${v.number}`, label: `${m.name} · version ${v.number} (${p.slug})`, project: p.slug })));
  });
  return { models, loading: projects.isLoading || lists.some((l) => l.isLoading) };
}

// ---------------------------------------------------------------------------------------------------- errors

type Help = { message: string; actions?: ReactNode };

/** An API failure in the user's terms, with the way forward (DESIGN.md §8). */
export function explain(e: unknown, ctx: { org: string; exp?: string; onReload?: () => void }): Help {
  if (!(e instanceof ApiError)) return { message: "Something went wrong talking to the server. Check your connection and try again." };
  const reload = ctx.onReload ? (
    <button className="btn py-0.5" onClick={ctx.onReload}>
      Reload
    </button>
  ) : undefined;
  switch (e.code) {
    case "experiment.checksum":
      return { message: "This request changed while you were looking at it, so the approval was not recorded. Reload to review what is there now.", actions: reload };
    case "experiment.self_approval":
      return { message: "You asked for this run, and this experiment needs someone else to approve it. Ask another engineer to review it." };
    case "experiment.decided":
      return { message: "Someone already decided this request.", actions: reload };
    case "experiment.scenario_changed":
    case "experiment.simulator_changed":
      return {
        message: "The simulation host now describes this scenario differently from when the version was created, so nothing was started. Make a new version from the current scenario.",
        actions: ctx.exp ? (
          <Link className="btn py-0.5" href={`/experiments?org=${ctx.org}&exp=${ctx.exp}&edit=1`}>
            Make a changed version
          </Link>
        ) : undefined,
      };
    case "experiment.host_unreachable":
    case "experiment.environment_unavailable":
      return { message: "The simulation host did not answer. Make sure it is running, then try again.", actions: reload };
    case "experiment.no_host":
      return {
        message: "This environment has no simulation host yet. Run discovery on it in the Hardware Hub first.",
        actions: (
          <Link className="btn py-0.5" href={`/hardware?org=${ctx.org}`}>
            Open the Hardware Hub
          </Link>
        ),
      };
    case "forbidden":
      return { message: "Your role in this workspace does not allow that. An engineer can." };
    case "conflict":
      return { message: "An experiment with that name already exists in this workspace. Pick another name." };
    default:
      return { message: e.message };
  }
}

export function ErrorNotice({ error, org, exp, onReload }: { error: unknown; org: string; exp?: string; onReload?: () => void }) {
  if (!error) return null;
  const h = explain(error, { org, exp, onReload });
  return (
    <Notice tone="bad">
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span>{h.message}</span>
        {h.actions}
      </span>
    </Notice>
  );
}

// ------------------------------------------------------------------------------------------------- stage rail

export type Stage = "approval" | "running" | "results";

/** Where a request is in the journey: what is done, what is happening now, what is still to come. */
export function StageRail({ detail }: { detail: Pick<ExperimentRequestDetail, "state" | "trials" | "trials_done"> }) {
  const approved = detail.state === "approved";
  const rejected = detail.state === "rejected";
  const finished = approved && detail.trials_done >= detail.trials;
  const steps: { label: string; state: "done" | "now" | "later" | "stopped" }[] = [
    { label: "Configured", state: "done" },
    { label: rejected ? "Rejected" : "Approved", state: rejected ? "stopped" : approved ? "done" : "now" },
    { label: "Run", state: rejected ? "later" : finished ? "done" : approved ? "now" : "later" },
    { label: "Results", state: finished ? "now" : "later" },
  ];
  return (
    <ol aria-label="Progress of this run" className="flex flex-wrap items-center gap-x-1 gap-y-1 text-[12px]">
      {steps.map((s, i) => (
        <li key={s.label} aria-current={s.state === "now" ? "step" : undefined} className="flex items-center gap-1">
          {i > 0 && <span aria-hidden className="mx-1 h-px w-5 bg-line" />}
          <span
            className={clsx(
              "rounded-sm px-1.5 py-0.5",
              s.state === "now" && "bg-accent-soft font-medium text-accent",
              s.state === "done" && "text-ink",
              s.state === "later" && "text-faint",
              s.state === "stopped" && "bg-bad-soft font-medium text-bad",
            )}
          >
            {s.state === "done" ? "✓ " : ""}
            {s.label}
          </span>
        </li>
      ))}
    </ol>
  );
}

export function Progress({ done, total, label }: { done: number; total: number; label: string }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="flex items-center gap-3 text-[13px]">
      <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} className="h-1.5 w-48 overflow-hidden rounded-sm bg-sunken">
        <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <span className="num text-muted">
        {done} of {total}
      </span>
    </div>
  );
}

export function SimulatedBadge() {
  return <Badge tone="warn">SIMULATED EVIDENCE</Badge>;
}

export function Crumbs({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-2 flex flex-wrap items-center gap-1 text-[12px] text-muted">
      {items.map((c, i) => (
        <span key={c.label} className="flex items-center gap-1">
          {i > 0 && <span aria-hidden>/</span>}
          {c.href ? (
            <Link className="hover:text-ink hover:underline" href={c.href}>
              {c.label}
            </Link>
          ) : (
            <span aria-current="page" className="text-ink">
              {c.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
