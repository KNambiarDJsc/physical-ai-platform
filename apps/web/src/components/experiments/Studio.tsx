"use client";

import { StudioModes } from "../StudioModes";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Notice } from "../AppShell";
import { RequireIdentity } from "../Identity";
import { OrgSelect, useOrg } from "../Workspace";
import { Configure } from "./Configure";
import { useExperiments } from "./common";
import { ExperimentList, ExperimentView, RequestView } from "./Views";

export function StudioView() {
  return (
    <RequireIdentity>
      <Studio />
    </RequireIdentity>
  );
}

/** The Experiment Studio: pick an environment, configure, approve, run, inspect, compare. State lives in the URL. */
function Studio() {
  const { me, orgs, org, role, select } = useOrg();
  const params = useSearchParams();
  const router = useRouter();
  const exps = useExperiments(org);
  const exp = params.get("exp");
  const request = params.get("request");
  const edit = params.get("edit");
  const saved = params.get("saved");
  const go = (q: Record<string, string | null>) => {
    const next = new URLSearchParams({ org: org ?? "" });
    for (const [k, v] of Object.entries(q)) if (v) next.set(k, v);
    router.push(`/experiments?${next.toString()}`);
  };
  if (me.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  if (!org)
    return (
      <Notice tone="info">
        You have no workspace yet. Start on the{" "}
        <Link className="underline" href="/onboarding">
          Get started
        </Link>{" "}
        page.
      </Notice>
    );
  const editing = exp && edit ? exps.data?.find((e) => e.slug === exp) : undefined;
  const editVersion = editing?.versions.find((v) => v.number === Number(edit)) ?? editing?.versions.at(-1);
  return (
    <>
      <StudioModes org={org} />
      {orgs.length > 1 && (
        <div className="mb-3 flex justify-end">
          <OrgSelect orgs={orgs} org={org} select={select} />
        </div>
      )}
      {saved && exp && !request && !edit && (
        <div className="mb-4">
          <Notice tone="info">Version {saved} is saved. Ask to run it below, and an engineer will review exactly this version.</Notice>
        </div>
      )}
      {params.get("new") ? (
        <Configure org={org} role={role} onSaved={(slug, n) => go({ exp: slug, saved: String(n) })} onCancel={() => go({})} />
      ) : exp && edit ? (
        exps.isLoading || !editing || !editVersion ? (
          <p className="text-[13px] text-muted">{exps.isLoading ? "Loading…" : "That experiment or version was not found."}</p>
        ) : (
          <Configure org={org} role={role} existing={{ exp: editing, version: editVersion }} onSaved={(slug, n) => go({ exp: slug, saved: String(n) })} onCancel={() => go({ exp })} />
        )
      ) : exp && request ? (
        <RequestView org={org} role={role} slug={exp} id={request} onAskAgain={(id) => go({ exp, request: id })} />
      ) : exp ? (
        <ExperimentView org={org} role={role} slug={exp} onRequested={(id) => go({ exp, request: id })} />
      ) : (
        <ExperimentList org={org} role={role} />
      )}
    </>
  );
}
