"use client";

import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, type Project } from "@/lib/api/client";
import { Notice } from "./AppShell";
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
  const [organizationFormOpen, setOrganizationFormOpen] = useState(false);
  const [projectFormOrg, setProjectFormOrg] = useState<string | null>(null);
  const projects = useQueries({
    queries: orgs.map((o) => ({
      queryKey: ["projects", o.slug],
      queryFn: () => api<Project[]>(`/api/v1/orgs/${o.slug}/projects`),
    })),
  });

  if (me.isLoading) return <p className="text-[14px] text-muted">Loading workspaces…</p>;
  if (me.error) return <Notice tone="bad">Could not reach the API: {me.error.message}</Notice>;

  if (orgs.length === 0) {
    return (
      <section className="max-w-3xl py-4" aria-labelledby="empty-workspaces-title">
        <h2 id="empty-workspaces-title" className="text-[clamp(1.5rem,3vw,2.25rem)] font-medium leading-tight tracking-[-0.04em]">
          Start with a workspace.
        </h2>
        <p className="mt-3 max-w-[58ch] text-[16px] leading-relaxed text-muted">
          Create an organization to group projects, environments and verified runs.
        </p>
        {!organizationFormOpen ? (
          <button type="button" className="btn btn-primary mt-7 min-h-10" aria-expanded="false" aria-controls="new-organization-form" onClick={() => setOrganizationFormOpen(true)}>
            Create organization
          </button>
        ) : (
          <div id="new-organization-form" className="mt-7 max-w-2xl rounded-md bg-panel p-5">
            <div className="mb-4 flex items-center justify-between gap-4">
              <h3 className="text-[17px] font-medium">New organization</h3>
              <button type="button" className="btn min-h-9" onClick={() => setOrganizationFormOpen(false)}>Close</button>
            </div>
            <NewOrganization />
          </div>
        )}
      </section>
    );
  }

  return (
    <div className="max-w-[1440px] space-y-12">
      {orgs.map((org, index) => {
        const query = projects[index];
        const projectCount = query?.data?.length;
        return (
          <section key={org.slug} className="grid gap-x-12 gap-y-5 lg:grid-cols-[minmax(13rem,0.85fr)_minmax(0,2fr)]" aria-labelledby={`org-${org.slug}`}>
            <div className="min-w-0 pt-2">
              <h2 id={`org-${org.slug}`} className="break-words text-[clamp(1.35rem,2.4vw,2rem)] font-medium leading-tight tracking-[-0.035em]">
                {org.slug}
              </h2>
              <p className="mt-2 text-[14px] text-muted">Your role: {org.role}</p>
            </div>

            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline justify-between gap-x-5 gap-y-2">
                <h3 className="text-[19px] font-medium tracking-[-0.025em]">Projects</h3>
                {typeof projectCount === "number" && <span className="text-[13px] text-muted">{projectCount} {projectCount === 1 ? "project" : "projects"}</span>}
                {org.role === "admin" && (
                  <button
                    type="button"
                    className="btn btn-primary min-h-10 whitespace-nowrap"
                    aria-expanded={projectFormOrg === org.slug}
                    aria-controls={`new-project-${org.slug}`}
                    onClick={() => setProjectFormOrg((current) => current === org.slug ? null : org.slug)}
                  >
                    {projectFormOrg === org.slug ? "Close" : "New project"}
                  </button>
                )}
              </div>

              {query?.isLoading && <p className="mt-4 text-[14px] text-muted" role="status">Loading projects…</p>}
              {query?.error && <div className="mt-4"><Notice tone="bad">{query.error.message}</Notice></div>}
              {query?.data && query.data.length === 0 && (
                <p className="mt-4 max-w-[56ch] text-[14px] leading-relaxed text-muted">
                  No projects yet. Create one to connect a system and start collecting run evidence.
                </p>
              )}
              {query?.data && query.data.length > 0 && (
                <ul className="mt-3 space-y-1">
                  {query.data.map((project) => (
                    <li key={project.id} className="group flex flex-col gap-2 rounded-md px-3 py-3 transition-colors hover:bg-panel sm:flex-row sm:items-center sm:justify-between sm:gap-5">
                      <Link className="min-w-0 flex-1 rounded-sm" href={`/o/${org.slug}/p/${project.slug}`}>
                        <span className="block text-[17px] font-medium tracking-[-0.02em] text-ink group-hover:text-accent">{project.name}</span>
                        <span className="mt-1 block text-[13px] text-muted">{project.description || `${org.slug} / ${project.slug}`}</span>
                      </Link>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 sm:shrink-0">
                        <Link className="inline-flex min-h-9 items-center rounded-sm text-[13px] font-medium text-muted hover:text-accent" href={{ pathname: "/twin", query: { org: org.slug, project: project.slug } }}>Explore system</Link>
                        <Link className="inline-flex min-h-9 items-center rounded-sm text-[13px] font-medium text-muted hover:text-accent" href={{ pathname: "/experiments", query: { org: org.slug } }}>Experiments</Link>
                        <Link className="inline-flex min-h-9 items-center rounded-sm text-[13px] font-medium text-muted hover:text-accent" href={{ pathname: "/runs", query: { org: org.slug } }}>Run history</Link>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {projectFormOrg === org.slug && (
                <div id={`new-project-${org.slug}`} className="mt-4 rounded-md bg-panel p-5">
                  <NewProject org={org.slug} />
                </div>
              )}
            </div>
          </section>
        );
      })}

      <div className="pt-2">
        {!organizationFormOpen ? (
          <button type="button" className="btn min-h-9 border-0 bg-transparent px-2 text-accent hover:bg-hover" onClick={() => setOrganizationFormOpen(true)}>
            Create organization
          </button>
        ) : (
          <div className="max-w-2xl rounded-md bg-panel p-5">
            <div className="mb-4 flex items-center justify-between gap-4">
              <h2 className="text-[17px] font-medium">New organization</h2>
              <button type="button" className="btn min-h-9" onClick={() => setOrganizationFormOpen(false)}>Close</button>
            </div>
            <NewOrganization />
          </div>
        )}
      </div>
    </div>
  );
}

const input = "field min-h-10";
const button = "btn btn-primary min-h-10";
const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;

function SlugForm({
  idPrefix,
  what,
  submit,
}: {
  idPrefix: string;
  what: string;
  submit: (slug: string, name: string) => Promise<unknown>;
}) {
  const qc = useQueryClient();
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const mutation = useMutation({
    mutationFn: () => submit(slug, name),
    onSuccess: () => {
      setSlug("");
      setName("");
      void qc.invalidateQueries();
    },
  });
  const valid = SLUG.test(slug) && name.trim().length > 0;

  return (
    <form className="flex flex-wrap items-end gap-4" onSubmit={(event: FormEvent) => (event.preventDefault(), mutation.mutate())}>
      <label className="text-[13px] text-muted" htmlFor={`${idPrefix}-name`}>
        {what} name
        <input id={`${idPrefix}-name`} className={`${input} mt-1 block`} value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <label className="text-[13px] text-muted" htmlFor={`${idPrefix}-slug`}>
        {what} slug
        <input id={`${idPrefix}-slug`} className={`${input} num mt-1 block`} placeholder="lowercase-and-dashes" value={slug} onChange={(event) => setSlug(event.target.value.trim())} />
      </label>
      <button className={button} disabled={!valid || mutation.isPending}>
        Create {what.toLowerCase()}
      </button>
      {slug && !SLUG.test(slug) && <span className="text-[13px] text-bad">Use lowercase letters, digits and dashes.</span>}
      {!valid && !slug && !name && <span className="basis-full text-[13px] text-muted">The slug is permanent and appears in URLs.</span>}
      {mutation.error && <span className="text-[13px] text-bad">{mutation.error.message}</span>}
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
  return <SlugForm idPrefix="org" what="Organization" submit={(slug, name) => api("/api/v1/orgs", { method: "POST", body: JSON.stringify({ slug, name }) })} />;
}
