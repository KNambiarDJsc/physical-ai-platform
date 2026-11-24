"use client";

import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";
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
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {orgs.length === 0 && <Notice tone="info">You are not a member of any organization yet. Create one below.</Notice>}
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
                  <Link className="inline-flex min-h-7 items-center font-medium text-accent hover:underline" href={`/o/${o.slug}/p/${p.slug}`}>
                    {p.name}
                  </Link>
                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                    <Link className="inline-flex min-h-7 items-center text-accent underline" href={{ pathname: "/twin", query: { org: o.slug, project: p.slug } }}>Explore system</Link>
                    <Link className="inline-flex min-h-7 items-center text-accent underline" href={{ pathname: "/experiments", query: { org: o.slug } }}>Configure experiment</Link>
                    <Link className="inline-flex min-h-7 items-center text-accent underline" href={{ pathname: "/runs", query: { org: o.slug } }}>Investigate workspace runs</Link>
                  </div>
                  {p.description && <div className="text-xs text-muted">{p.description}</div>}
                </li>
              ))}
            </ul>
            {o.role === "admin" && <NewProject org={o.slug} />}
          </Panel>
        );
      })}
      <Panel title="New organization">
        <NewOrganization />
      </Panel>
    </div>
  );
}

const input = "field";
const button = "btn btn-primary";
const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;

function SlugForm({
  idPrefix,
  what,
  submit,
  alone,
}: {
  idPrefix: string;
  what: string;
  submit: (slug: string, name: string) => Promise<unknown>;
  /** The form is the whole panel: no divider above it. */
  alone?: boolean;
}) {
  const qc = useQueryClient();
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const m = useMutation({
    mutationFn: () => submit(slug, name),
    onSuccess: () => {
      setSlug("");
      setName("");
      void qc.invalidateQueries();
    },
  });
  const valid = SLUG.test(slug) && name.trim().length > 0;
  return (
    <form
      className={alone ? "flex flex-wrap items-end gap-2" : "mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3"}
      onSubmit={(e: FormEvent) => (e.preventDefault(), m.mutate())}
    >
      <label className="text-xs text-muted" htmlFor={`${idPrefix}-name`}>
        {what} name
        <input id={`${idPrefix}-name`} className={`${input} mt-1 block`} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="text-xs text-muted" htmlFor={`${idPrefix}-slug`}>
        {what} slug
        <input id={`${idPrefix}-slug`} className={`${input} num mt-1 block`} placeholder="lowercase-and-dashes" value={slug} onChange={(e) => setSlug(e.target.value.trim())} />
      </label>
      <button className={button} disabled={!valid || m.isPending}>
        Create {what.toLowerCase()}
      </button>
      {slug && !SLUG.test(slug) && <span className="text-xs text-bad">lowercase letters, digits and dashes</span>}
      {!valid && !slug && !name && <span className="basis-full text-xs text-muted">Enter a name and a slug to create one. The slug is permanent and appears in URLs.</span>}
      {m.error && <span className="text-xs text-bad">{m.error.message}</span>}
    </form>
  );
}

function NewProject({ org }: { org: string }) {
  return (
    <SlugForm
      idPrefix={`project-${org}`}
      what="Project"
      submit={(slug, name) => api(`/api/v1/orgs/${org}/projects`, { method: "POST", body: JSON.stringify({ slug, name }) })}
    />
  );
}

function NewOrganization() {
  return <SlugForm alone idPrefix="org" what="Organization" submit={(slug, name) => api("/api/v1/orgs", { method: "POST", body: JSON.stringify({ slug, name }) })} />;
}
