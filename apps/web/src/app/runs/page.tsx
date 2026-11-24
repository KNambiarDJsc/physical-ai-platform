"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { RequireIdentity } from "@/components/Identity";
import { OrgSelect, RUN_STATE, useOrg, useRuns } from "@/components/Workspace";
import { Time } from "@/components/ui";

function RunHistory() {
  const { org, orgs, select } = useOrg();
  const runs = useRuns(org);
  const [query, setQuery] = useState("");
  const [visible, setVisible] = useState(40);
  const matches = runs.data?.filter((r) =>
    [r.workflow_name, r.environment, r.workflow, r.id, r.state, RUN_STATE[r.state], r.verdict, r.created_at].join(" ").toLowerCase().includes(query.trim().toLowerCase())
  );
  return <section className="mx-auto max-w-5xl space-y-5">
    <header className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-semibold">Run history</h1><OrgSelect org={org} orgs={orgs} select={select} /></header>
    <label className="block text-sm">Find a run<input type="search" className="field mt-1 block w-full" placeholder="Workflow, environment, run ID or outcome" value={query} onChange={(e) => { setQuery(e.target.value); setVisible(40); }} /></label>
    {runs.data?.length === 200 && <p className="text-sm text-muted">Search covers the latest 200 workflow runs.</p>}
    {!org ? <Link className="text-accent underline" href="/onboarding">Choose a workspace</Link> :
      runs.isLoading ? <p role="status">Loading runs…</p> :
      runs.isError ? <p role="alert">Run history could not load. <button className="btn" onClick={() => void runs.refetch()}>Retry</button></p> :
      !matches?.length ? <p>{runs.data?.length ? "No runs match this search." : "This workspace has no workflow runs yet."}</p> :
      <ul className="divide-y divide-line border-y border-line">{matches.slice(0, visible).map((r) => <li key={r.id}>
        <Link className="grid gap-2 px-2 py-4 hover:bg-panel sm:grid-cols-[2fr_1fr_1fr]" href={{ pathname: "/workbench", query: { org, run: r.id } }}>
          <span><strong>{r.workflow_name}</strong> · {r.environment}<span className="num block break-all text-xs text-muted">{r.id}</span></span>
          <span>{RUN_STATE[r.state] ?? r.state}<span className="block text-xs text-muted">{r.verdict ?? "No stored verdict"}</span></span>
          <span className="num text-sm"><Time iso={r.created_at} /></span>
        </Link></li>)}</ul>}
    {matches && matches.length > visible && <button className="btn" onClick={() => setVisible(visible + 40)}>Show more runs</button>}
  </section>;
}

export default function Page() {
  return <Suspense><RequireIdentity><RunHistory /></RequireIdentity></Suspense>;
}
