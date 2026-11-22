"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api, orgPath, type Project, type Schemas } from "@/lib/api/client";
import type { ExperimentOut, ExperimentVersion } from "@/lib/experiments";
import { Panel } from "../AppShell";
import { Badge, Table, Td, Time, VerdictBadge } from "../ui";
import { ErrorNotice } from "./common";

type ReleaseEvaluation = Schemas["ReleaseEvaluationOut"];
type Arm = { key: string; title?: string; role: "baseline" | "candidate" };

const STATE: Record<string, string> = { queued: "Waiting for the worker", running: "The engine is comparing", succeeded: "Done", failed: "Failed", cancelled: "Cancelled" };

/**
 * From contract violations to a release verdict. The page computes nothing: it asks the platform to judge two setups as
 * releases, which queues an ordinary evaluation job, and shows the engine's verdict and reasons verbatim.
 */
export function ReleaseVerdict({ org, exp, version, canJudge }: { org: string; exp: ExperimentOut; version: ExperimentVersion; canJudge: boolean }) {
  const qc = useQueryClient();
  const arms = (version.spec as { arms: Arm[] }).arms;
  const model = (version.spec as { model?: { project: string } }).model;
  const [baseline, setBaseline] = useState(arms.find((a) => a.role === "baseline")?.key ?? arms[0]?.key ?? "");
  const [candidate, setCandidate] = useState(arms.find((a) => a.role === "candidate")?.key ?? arms[1]?.key ?? "");
  const projects = useQuery({ queryKey: ["projects", org], queryFn: () => api<Project[]>(`${orgPath(org)}/projects`) });
  const [project, setProject] = useState(model?.project ?? "");
  const chosenProject = project || projects.data?.[0]?.slug || "";
  const url = `${orgPath(org)}/experiments/${exp.slug}/release-evaluations`;
  const list = useQuery({
    queryKey: ["release-evaluations", org, exp.slug],
    queryFn: () => api<ReleaseEvaluation[]>(url),
    refetchInterval: (q) => (q.state.data?.some((e) => e.state === "queued" || e.state === "running") ? 2000 : false),
  });
  const judge = useMutation({
    mutationFn: () => api<ReleaseEvaluation>(url, { method: "POST", body: JSON.stringify({ version: version.number, baseline_arm: baseline, candidate_arm: candidate, project: chosenProject }) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["release-evaluations", org, exp.slug] }),
  });
  const title = (k: string) => arms.find((a) => a.key === k)?.title || k;
  if (arms.length < 2) return null;
  return (
    <Panel title="Release verdict">
      <div className="space-y-3 text-[13px]">
        <p className="max-w-3xl text-muted">
          A violated trial is one run breaking the contract. Whether a setup is a regression is a statistical question: the engine answers it here from every finished trial of this version&apos;s approved runs, treating the two setups as releases. With few trials its answer is usually &ldquo;insufficient evidence&rdquo;; run the experiment again to add trials.
        </p>
        {canJudge && (
          <div className="flex flex-wrap items-end gap-3">
            <label>
              <span className="mb-1 block text-muted">Baseline</span>
              <select className="field" value={baseline} onChange={(e) => setBaseline(e.target.value)}>
                {arms.map((a) => (
                  <option key={a.key} value={a.key}>
                    {a.title || a.key}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="mb-1 block text-muted">Candidate</span>
              <select className="field" value={candidate} onChange={(e) => setCandidate(e.target.value)}>
                {arms.map((a) => (
                  <option key={a.key} value={a.key}>
                    {a.title || a.key}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="mb-1 block text-muted">Project</span>
              <select className="field" value={chosenProject} onChange={(e) => setProject(e.target.value)}>
                {(projects.data ?? []).map((p) => (
                  <option key={p.slug} value={p.slug}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <button className="btn" disabled={judge.isPending || baseline === candidate || !chosenProject} onClick={() => judge.mutate()}>
              {judge.isPending ? "Submitting…" : `Judge version ${version.number} as releases`}
            </button>
            {baseline === candidate && <span className="pb-1.5 text-[12px] text-muted">Choose two different setups.</span>}
          </div>
        )}
        {judge.error && <ErrorNotice error={judge.error} org={org} exp={exp.slug} />}
        {list.error && <ErrorNotice error={list.error} org={org} onReload={() => void list.refetch()} />}
        {list.data && list.data.length > 0 && (
          <Table head={["Judged", "Version", "Baseline vs candidate", "Trials", "State", "Engine verdict", ""]} caption="Release verdicts">
            {list.data.map((e) => (
              <tr key={e.id}>
                <Td>
                  <Time iso={e.created_at} />
                </Td>
                <Td className="num">{e.version}</Td>
                <Td className="whitespace-normal">
                  {title(e.baseline_arm)} vs {title(e.candidate_arm)}
                </Td>
                <Td className="num">
                  {e.trials.baseline ?? 0} and {e.trials.candidate ?? 0}
                </Td>
                <Td>{STATE[e.state] ?? e.state}</Td>
                <Td className="whitespace-normal">
                  {e.verdict?.verdict ? (
                    <span className="block">
                      <VerdictBadge verdict={String(e.verdict.verdict)} />
                      {Array.isArray(e.verdict.reasons) && e.verdict.reasons.length > 0 && <span className="mt-0.5 block text-[12px] text-muted">{(e.verdict.reasons as string[]).join("; ")}</span>}
                    </span>
                  ) : e.state === "failed" ? (
                    <Badge tone="bad">no verdict</Badge>
                  ) : (
                    "—"
                  )}
                </Td>
                <Td>
                  <Link className="text-accent hover:underline" href={`/o/${org}/p/${e.project}/e/${e.evaluation_id}`}>
                    Open in Releases
                  </Link>
                </Td>
              </tr>
            ))}
          </Table>
        )}
        {list.data && list.data.length === 0 && <p className="text-muted">Not judged yet.</p>}
      </div>
    </Panel>
  );
}
