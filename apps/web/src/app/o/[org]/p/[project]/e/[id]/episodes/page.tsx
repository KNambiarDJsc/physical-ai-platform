"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, use, useState } from "react";
import { Notice, PageHeader } from "@/components/AppShell";
import { EpisodeDetailView } from "@/components/EpisodeDetailView";
import { RequireIdentity } from "@/components/Identity";
import { ClassBadge, Table, Td } from "@/components/ui";
import { api, projectPath, type EpisodeDetail, type EpisodePage, type Evaluation } from "@/lib/api/client";
import { CLASS_LABEL } from "@/lib/format";

type Params = { org: string; project: string; id: string };
const PAGE = 50;

export default function EpisodesPage({ params }: { params: Promise<Params> }) {
  const p = use(params);
  return (
    <RequireIdentity>
      <Suspense>
        <Episodes {...p} />
      </Suspense>
    </RequireIdentity>
  );
}

function Episodes({ org, project, id }: Params) {
  const search = useSearchParams();
  const base = `${projectPath(org, project)}/evaluations/${id}`;
  const [cls, setCls] = useState(search.get("outcome_class") ?? "");
  const [release, setRelease] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const job = useQuery({ queryKey: ["evaluation", id], queryFn: () => api<Evaluation>(base) });
  const qs = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (cls) qs.set("outcome_class", cls);
  if (release) qs.set("release_id", release);
  const page = useQuery({ queryKey: ["episodes", id, qs.toString()], queryFn: () => api<EpisodePage>(`${base}/episodes?${qs}`) });
  const detail = useQuery({
    queryKey: ["episode", selected],
    queryFn: () => api<EpisodeDetail>(`${base}/episodes/${selected}`),
    enabled: !!selected,
  });
  const j = job.data;
  const releaseLabel = (rid: string) => (j ? (rid === j.baseline_release_id ? j.baseline_label : j.candidate_label) : rid);
  const sel = "rounded-md border border-line bg-panel px-2 py-1.5 text-[13px]";
  return (
    <>
      <PageHeader
        title="Episodes"
        subtitle={
          <Link className="text-accent hover:underline" href={`/o/${org}/p/${project}/e/${id}`}>
            {j ? `${j.baseline_label} → ${j.candidate_label}` : "evaluation"}
          </Link>
        }
      />
      <div className="mb-3 flex flex-wrap gap-2">
        <label className="text-xs text-muted">
          Outcome{" "}
          <select className={sel} value={cls} onChange={(e) => (setCls(e.target.value), setOffset(0))}>
            <option value="">all</option>
            {Object.entries(CLASS_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-muted">
          Release{" "}
          <select className={sel} value={release} onChange={(e) => (setRelease(e.target.value), setOffset(0))}>
            <option value="">both</option>
            {j && <option value={j.baseline_release_id}>{j.baseline_label}</option>}
            {j && <option value={j.candidate_release_id}>{j.candidate_label}</option>}
          </select>
        </label>
      </div>
      {page.error && <Notice tone="bad">{page.error.message}</Notice>}
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-lg border border-line bg-panel p-2">
          {page.data && (
            <>
              <Table head={["Episode", "Release", "Robot", "Scenario", "Reported", "Verdict", "Outcome"]} caption="Episodes">
                {page.data.items.map((e) => (
                  <tr key={e.id} className={selected === e.id ? "bg-accent-soft" : "hover:bg-sunken"}>
                    <Td>
                      <button className="num text-accent hover:underline" onClick={() => setSelected(e.id)}>
                        {e.episode_key}
                      </button>
                    </Td>
                    <Td>{releaseLabel(e.release_id)}</Td>
                    <Td>{e.robot}</Td>
                    <Td className="num">{e.scenario ?? "—"}</Td>
                    <Td className="num">{e.reported}</Td>
                    <Td className="num">{e.verdict ?? "—"}</Td>
                    <Td>
                      <ClassBadge value={e.outcome_class} />
                    </Td>
                  </tr>
                ))}
              </Table>
              <div className="mt-2 flex items-center justify-between px-2 text-xs text-muted">
                <span className="num">
                  {page.data.total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE, page.data.total)} of {page.data.total}
                </span>
                <span className="space-x-2">
                  <button disabled={offset === 0} className="disabled:opacity-40" onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                    Previous
                  </button>
                  <button disabled={offset + PAGE >= page.data.total} className="disabled:opacity-40" onClick={() => setOffset(offset + PAGE)}>
                    Next
                  </button>
                </span>
              </div>
            </>
          )}
        </div>
        <div>
          {!selected && <Notice tone="info">Select an episode to see its evidence and the verifier&apos;s reasons.</Notice>}
          {detail.data && <EpisodeDetailView ep={detail.data} />}
          {detail.error && <Notice tone="bad">{detail.error.message}</Notice>}
        </div>
      </div>
    </>
  );
}
