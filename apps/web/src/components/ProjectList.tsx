"use client";

import { useQueries } from "@tanstack/react-query";
import Link from "next/link";
import { api, type Project } from "@/lib/api/client";
import { Notice, Panel } from "./AppShell";
import { RequireIdentity, useMe } from "./Identity";

export function ProjectList() {
  return (
    <RequireIdentity>
      <Projects />
    </RequireIdentity>
  );
}

function Projects() {
  const me = useMe();
  const orgs = me.data?.organizations ?? [];
  const projects = useQueries({
    queries: orgs.map((o) => ({
      queryKey: ["projects", o.slug],
      queryFn: () => api<Project[]>(`/api/v1/orgs/${o.slug}/projects`),
    })),
  });
  if (me.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  if (me.error) return <Notice tone="bad">Could not reach the API: {me.error.message}</Notice>;
  if (orgs.length === 0) return <Notice tone="info">You are not a member of any organization yet.</Notice>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {orgs.map((o, i) => {
        const q = projects[i];
        return (
          <Panel key={o.slug} title={`${o.slug} · ${o.role}`}>
            {q?.isLoading && <p className="text-[13px] text-muted">Loading projects…</p>}
            {q?.error && <Notice tone="bad">{q.error.message}</Notice>}
            {q?.data && q.data.length === 0 && <p className="text-[13px] text-muted">No projects yet.</p>}
            <ul className="divide-y divide-line">
              {q?.data?.map((p) => (
                <li key={p.id} className="py-2">
                  <Link className="font-medium text-accent hover:underline" href={`/o/${o.slug}/p/${p.slug}`}>
                    {p.name}
                  </Link>
                  {p.description && <div className="text-xs text-muted">{p.description}</div>}
                </li>
              ))}
            </ul>
          </Panel>
        );
      })}
    </div>
  );
}
