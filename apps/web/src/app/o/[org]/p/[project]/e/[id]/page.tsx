"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { Notice, PageHeader, Panel } from "@/components/AppShell";
import { ComparisonView } from "@/components/ComparisonView";
import { RequireIdentity } from "@/components/Identity";
import { StateBadge } from "@/components/ui";
import { api, download, projectPath, type ComparisonOut, type Evaluation } from "@/lib/api/client";

type Params = { org: string; project: string; id: string };

export default function EvaluationPage({ params }: { params: Promise<Params> }) {
  const p = use(params);
  return (
    <RequireIdentity>
      <Evaluation {...p} />
    </RequireIdentity>
  );
}

function Evaluation({ org, project, id }: Params) {
  const base = `${projectPath(org, project)}/evaluations/${id}`;
  const job = useQuery({
    queryKey: ["evaluation", id],
    queryFn: () => api<Evaluation>(base),
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.state) ? 1500 : false),
  });
  const done = job.data?.state === "succeeded";
  const cmp = useQuery({ queryKey: ["comparison", id], queryFn: () => api<ComparisonOut>(`${base}/comparison`), enabled: done });
  const j = job.data;
  return (
    <>
      <PageHeader
        title={j ? `${j.baseline_label} → ${j.candidate_label}` : "Evaluation"}
        subtitle={
          <span className="flex items-center gap-2">
            <Link className="text-accent hover:underline" href={`/o/${org}/p/${project}`}>
              {org} / {project}
            </Link>
            {j && <StateBadge state={j.state} />}
            {j && <span className="num text-xs text-faint">attempt {j.attempts} of {j.max_attempts}</span>}
          </span>
        }
        actions={done ? <ReportActions base={base} id={id} /> : undefined}
      />
      {job.isLoading && <p className="text-[13px] text-muted">Loading…</p>}
      {job.error && <Notice tone="bad">{job.error.message}</Notice>}
      {j && (j.state === "queued" || j.state === "running") && (
        <Panel>
          <p className="text-[13px] text-muted">
            {j.state === "queued" ? "Waiting for an evaluation worker." : "The engine is verifying outcomes and comparing releases."} This
            page updates by itself.
          </p>
        </Panel>
      )}
      {j?.state === "failed" && (
        <Notice tone="bad">
          Evaluation failed: <span className="num">{String(j.error?.code ?? "")}</span> — {String(j.error?.message ?? "")}
        </Notice>
      )}
      {j?.state === "cancelled" && <Notice tone="info">This evaluation was cancelled.</Notice>}
      {cmp.error && <Notice tone="bad">{cmp.error.message}</Notice>}
      {cmp.data && <ComparisonView data={cmp.data} episodesHref={`/o/${org}/p/${project}/e/${id}/episodes`} />}
    </>
  );
}

/** Downloads the reproducible JSON report and the HTML report rendered from it. */
function ReportActions({ base, id }: { base: string; id: string }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const get = async (fmt: "html" | "json") => {
    setBusy(fmt);
    setErr(null);
    try {
      await download(`${base}/report.${fmt}`, `evaluation-${id}.${fmt}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  const btn = "btn";
  return (
    <div className="flex items-center gap-2">
      <button className={btn} disabled={!!busy} onClick={() => get("html")}>
        {busy === "html" ? "Preparing…" : "Download HTML report"}
      </button>
      <button className={btn} disabled={!!busy} onClick={() => get("json")}>
        {busy === "json" ? "Preparing…" : "Download JSON report"}
      </button>
      {err && (
        <span role="alert" className="text-xs text-bad">
          {err}
        </span>
      )}
    </div>
  );
}
