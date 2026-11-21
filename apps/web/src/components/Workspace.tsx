"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { api, orgPath, type Device, type Environment, type Workflow, type WorkflowRun } from "@/lib/api/client";
import { useMe } from "./Identity";

/** The workspace (organization) a page works in: `?org=` in the URL, else the caller's first one. */
export function useOrg() {
  const me = useMe();
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const orgs = me.data?.organizations ?? [];
  const wanted = params.get("org");
  const current = orgs.find((o) => o.slug === wanted) ?? orgs[0] ?? null;
  const select = (slug: string) => {
    const q = new URLSearchParams(params.toString());
    q.set("org", slug);
    router.replace(`${path}?${q.toString()}`);
  };
  return { me, orgs, org: current?.slug ?? null, role: current?.role ?? null, select };
}

export function OrgSelect({ orgs, org, select }: { orgs: { slug: string }[]; org: string | null; select: (s: string) => void }) {
  if (orgs.length < 2 || !org) return null;
  return (
    <label className="flex items-center gap-2 text-[12px] text-muted">
      Workspace
      <select className="field py-1" value={org} onChange={(e) => select(e.target.value)}>
        {orgs.map((o) => (
          <option key={o.slug} value={o.slug}>
            {o.slug}
          </option>
        ))}
      </select>
    </label>
  );
}

export const useEnvironments = (org: string | null) =>
  useQuery({ queryKey: ["environments", org], queryFn: () => api<Environment[]>(`${orgPath(org!)}/environments`), enabled: !!org });

export const useDevices = (org: string | null) =>
  useQuery({ queryKey: ["devices", org], queryFn: () => api<Device[]>(`${orgPath(org!)}/devices`), enabled: !!org });

export const useWorkflows = (org: string | null) =>
  useQuery({ queryKey: ["workflows", org], queryFn: () => api<Workflow[]>(`${orgPath(org!)}/workflows`), enabled: !!org });

export const useRuns = (org: string | null) =>
  useQuery({
    queryKey: ["runs", org],
    queryFn: () => api<WorkflowRun[]>(`${orgPath(org!)}/workflow-runs`),
    enabled: !!org,
    refetchInterval: (q) => (q.state.data?.some((r) => r.state === "queued" || r.state === "running") ? 1000 : false),
  });

/** Plain-language labels for run and step states (DESIGN.md §9: say what happened). */
export const RUN_STATE: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Completed",
  failed: "Failed",
  outcome_unknown: "Outcome unknown",
  cancelled: "Cancelled",
  pending: "Pending",
  dispatching: "Sent, awaiting answer",
  completed: "Completed",
  refused: "Refused",
};
