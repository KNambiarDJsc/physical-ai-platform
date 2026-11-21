"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState, type FormEvent } from "react";
import { Notice, PageHeader, Panel } from "@/components/AppShell";
import { RequireIdentity } from "@/components/Identity";
import { StateBadge, Table, Td, VerdictBadge } from "@/components/ui";
import { api, projectPath, type Artifact, type Evaluation, type Mapping, type Release } from "@/lib/api/client";
import { shortDigest } from "@/lib/format";

type Params = { org: string; project: string };

export default function ProjectPage({ params }: { params: Promise<Params> }) {
  const p = use(params);
  return (
    <RequireIdentity>
      <Workspace {...p} />
    </RequireIdentity>
  );
}

const input = "field";
const button = "btn btn-primary";

function Workspace({ org, project }: Params) {
  const base = projectPath(org, project);
  const qc = useQueryClient();
  const releases = useQuery({ queryKey: ["releases", base], queryFn: () => api<Release[]>(`${base}/releases`) });
  const artifacts = useQuery({ queryKey: ["artifacts", base], queryFn: () => api<Artifact[]>(`${base}/artifacts`) });
  const mappings = useQuery({ queryKey: ["mappings", base], queryFn: () => api<Mapping[]>(`${base}/mappings`) });
  const evals = useQuery({
    queryKey: ["evaluations", base],
    queryFn: () => api<Evaluation[]>(`${base}/evaluations`),
    refetchInterval: (q) => (q.state.data?.some((e) => ["queued", "running"].includes(e.state)) ? 2000 : false),
  });
  const refresh = () => void qc.invalidateQueries();
  const sources = (artifacts.data ?? []).filter((a) => a.kind === "source");
  return (
    <>
      <PageHeader title={`${org} / ${project}`} subtitle="Release Intelligence" />
      {[releases, artifacts, mappings, evals].map((q, i) => q.error && <Notice key={i} tone="bad">{q.error.message}</Notice>)}
      <div className="space-y-4">
        <Panel title="Evaluations">
          {evals.data && evals.data.length === 0 && <p className="text-[13px] text-muted">No evaluations yet.</p>}
          {evals.data && evals.data.length > 0 && (
            <Table head={["Baseline → candidate", "State", "Reported", "Verified", "Episodes", "Created"]} caption="Evaluations">
              {evals.data.map((e) => (
                <tr key={e.id}>
                  <Td>
                    <Link className="font-medium text-accent hover:underline" href={`/o/${org}/p/${project}/e/${e.id}`}>
                      {e.baseline_label} → {e.candidate_label}
                    </Link>
                  </Td>
                  <Td>
                    <StateBadge state={e.state} />
                  </Td>
                  <Td>{e.summary?.verdict_reported ? <VerdictBadge verdict={String(e.summary.verdict_reported)} /> : "—"}</Td>
                  <Td>{e.summary?.verdict_verified ? <VerdictBadge verdict={String(e.summary.verdict_verified)} /> : "—"}</Td>
                  <Td num>{e.summary ? String(e.summary.episodes) : "—"}</Td>
                  <Td className="text-muted">{new Date(e.created_at).toLocaleString()}</Td>
                </tr>
              ))}
            </Table>
          )}
          <NewEvaluation base={base} org={org} project={project} releases={releases.data ?? []} artifacts={sources} mappings={mappings.data ?? []} />
        </Panel>
        <div className="grid gap-4 xl:grid-cols-3">
          <Panel title="Releases">
            <ul className="mb-3 divide-y divide-line text-[13px]">
              {releases.data?.map((r) => (
                <li key={r.id} className="py-1.5">
                  <span className="font-medium">{r.label}</span> <span className="text-xs text-muted">{r.kind}</span>
                  <div className="num text-xs text-faint">manifest {shortDigest(r.manifest_digest)}</div>
                </li>
              ))}
            </ul>
            <NewRelease base={base} onDone={refresh} />
          </Panel>
          <Panel title="Evidence">
            <ul className="mb-3 divide-y divide-line text-[13px]">
              {sources.map((a) => (
                <li key={a.id} className="py-1.5">
                  <span className="font-medium">{a.filename}</span>
                  <div className="num text-xs text-faint">
                    {shortDigest(a.sha256)} · {(a.size_bytes / 1024).toFixed(1)} KiB
                  </div>
                </li>
              ))}
            </ul>
            <Upload base={base} onDone={refresh} />
          </Panel>
          <Panel title="Mappings">
            <ul className="mb-3 divide-y divide-line text-[13px]">
              {mappings.data?.map((m) => (
                <li key={m.id} className="py-1.5">
                  <span className="font-medium">{m.name}</span> <span className="text-xs text-muted">v{m.version}</span>
                  <div className="num text-xs text-faint">{shortDigest(m.spec_sha256)}</div>
                </li>
              ))}
            </ul>
            <NewMapping base={base} onDone={refresh} />
          </Panel>
        </div>
      </div>
    </>
  );
}

function useAction<T>(fn: () => Promise<T>, onDone: (r: T) => void) {
  return useMutation({ mutationFn: fn, onSuccess: onDone });
}

function NewRelease({ base, onDone }: { base: string; onDone: () => void }) {
  const [label, setLabel] = useState("");
  const m = useAction(
    () =>
      api<Release>(`${base}/releases`, {
        method: "POST",
        body: JSON.stringify({ label, kind: "software", components: [{ kind: "software", name: "stack", version: label }] }),
      }),
    () => {
      setLabel("");
      onDone();
    },
  );
  return (
    <form className="flex gap-2" onSubmit={(e: FormEvent) => (e.preventDefault(), m.mutate())}>
      <label className="sr-only" htmlFor="release-label">Release label</label>
      <input id="release-label" className={`${input} flex-1`} placeholder="release label, e.g. 2.15.0" value={label} onChange={(e) => setLabel(e.target.value)} />
      <button className={button} disabled={!label || m.isPending}>Add</button>
      {m.error && <span className="text-xs text-bad">{m.error.message}</span>}
    </form>
  );
}

function Upload({ base, onDone }: { base: string; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const m = useAction(
    () => {
      const fd = new FormData();
      if (file) fd.append("file", file);
      return api<Artifact>(`${base}/artifacts`, { method: "POST", body: fd });
    },
    () => onDone(),
  );
  return (
    <form className="flex flex-wrap gap-2" onSubmit={(e: FormEvent) => (e.preventDefault(), m.mutate())}>
      <label className="sr-only" htmlFor="upload">Evidence file</label>
      <input id="upload" type="file" accept=".csv,.jsonl,.json" className="text-[13px]" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <button className={button} disabled={!file || m.isPending}>Upload</button>
      {m.error && <span className="text-xs text-bad">{m.error.message}</span>}
    </form>
  );
}

function NewMapping({ base, onDone }: { base: string; onDone: () => void }) {
  const [text, setText] = useState("");
  const m = useAction(() => api<Mapping>(`${base}/mappings`, { method: "POST", body: text }), () => {
    setText("");
    onDone();
  });
  return (
    <form className="space-y-2" onSubmit={(e: FormEvent) => (e.preventDefault(), m.mutate())}>
      <label className="sr-only" htmlFor="mapping">Mapping (pap.mapping/1 JSON)</label>
      <textarea id="mapping" className={`${input} num h-20 w-full text-xs`} placeholder='{"schema": "pap.mapping/1", ...}' value={text} onChange={(e) => setText(e.target.value)} />
      <button className={button} disabled={!text || m.isPending}>Add version</button>
      {m.error && <div className="text-xs text-bad">{m.error.message}</div>}
    </form>
  );
}

function NewEvaluation(props: { base: string; org: string; project: string; releases: Release[]; artifacts: Artifact[]; mappings: Mapping[] }) {
  const router = useRouter();
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const [mapping, setMapping] = useState("");
  const [baseArt, setBaseArt] = useState<string[]>([]);
  const [candArt, setCandArt] = useState<string[]>([]);
  const [taskType, setTaskType] = useState("");
  const [paired, setPaired] = useState(false);
  const [minKnown, setMinKnown] = useState("30");
  const m = useMutation({
    mutationFn: () =>
      api<Evaluation>(`${props.base}/evaluations`, {
        method: "POST",
        body: JSON.stringify({
          baseline_release_id: baseline,
          candidate_release_id: candidate,
          mapping_id: mapping,
          baseline_artifact_ids: baseArt,
          candidate_artifact_ids: candArt,
          config: { task_type: taskType, paired, min_known: Number(minKnown) },
        }),
      }),
    onSuccess: (e) => router.push(`/o/${props.org}/p/${props.project}/e/${e.id}`),
  });
  const ready = baseline && candidate && baseline !== candidate && mapping && baseArt.length && candArt.length && taskType && Number(minKnown) >= 1;
  const multi = (id: string, value: string[], set: (v: string[]) => void, label: string) => (
    <div>
      <label className="text-xs text-muted" htmlFor={id}>
        {label}
      </label>
      <select id={id} multiple className={`${input} mt-1 block h-20 w-full`} value={value} onChange={(e) => set(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {props.artifacts.map((a) => (
          <option key={a.id} value={a.id}>{a.filename} · {shortDigest(a.sha256)}</option>
        ))}
      </select>
    </div>
  );
  const one = (id: string, value: string, set: (v: string) => void, label: string, items: { id: string; text: string }[]) => (
    <div>
      <label className="text-xs text-muted" htmlFor={id}>
        {label}
      </label>
      <select id={id} className={`${input} mt-1 block w-full`} value={value} onChange={(e) => set(e.target.value)}>
        <option value="">Choose…</option>
        {items.map((i) => (
          <option key={i.id} value={i.id}>{i.text}</option>
        ))}
      </select>
    </div>
  );
  const rel = props.releases.map((r) => ({ id: r.id, text: r.label }));
  return (
    <form className="mt-4 border-t border-line pt-4" onSubmit={(e: FormEvent) => (e.preventDefault(), m.mutate())}>
      <h3 className="mb-2 text-[13px] font-semibold">New evaluation</h3>
      <div className="grid gap-3 md:grid-cols-3">
        {one("baseline", baseline, setBaseline, "Baseline release", rel)}
        {one("candidate", candidate, setCandidate, "Candidate release", rel)}
        {one("mapping-select", mapping, setMapping, "Mapping", props.mappings.map((x) => ({ id: x.id, text: `${x.name} v${x.version}` })))}
        {multi("baseline-evidence", baseArt, setBaseArt, "Baseline evidence")}
        {multi("candidate-evidence", candArt, setCandArt, "Candidate evidence")}
        <div className="space-y-2">
          <label className="block text-xs text-muted" htmlFor="task-type">
            Task type
            <input id="task-type" className={`${input} mt-1 block w-full`} value={taskType} onChange={(e) => setTaskType(e.target.value)} placeholder="e.g. pick_place" />
          </label>
          <label className="block text-xs text-muted" htmlFor="min-known">
            Minimum known units per release
            <input id="min-known" type="number" min={1} step={1} className={`${input} num mt-1 block w-full`} value={minKnown} onChange={(e) => setMinKnown(e.target.value)} />
          </label>
          <label className="flex items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={paired} onChange={(e) => setPaired(e.target.checked)} /> Also pair by scenario
          </label>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button className={button} disabled={!ready || m.isPending}>Start evaluation</button>
        {m.error && <span className="text-xs text-bad">{m.error.message}</span>}
      </div>
    </form>
  );
}
