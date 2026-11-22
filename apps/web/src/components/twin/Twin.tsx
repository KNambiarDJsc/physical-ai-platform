"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Eye, RotateCcw } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  apiBytes,
  orgPath,
  projectPath,
  type Device,
  type ModelVersion,
  type Project,
  type PropertyRead,
  type Recording,
  type RecordingDetail,
} from "@/lib/api/client";
import {
  jointValues,
  matchJoints,
  MODE_TEXT,
  observerBasePose,
  observerJoints,
  observerMode,
  sampleAt,
  sampleOther,
  compareOffset,
  baseGap,
  type Align,
  type Mode,
  type ObserverReads,
  type Pose,
  type Structure,
  type Track,
  type TwinEvent,
} from "@/lib/twin";
import { Notice } from "../AppShell";
import { RequireIdentity } from "../Identity";
import { Split } from "../Split";
import { Badge, ClassBadge } from "../ui";
import { VerdictBadge } from "../Workbench";
import { OrgSelect, useDevices, useOrg } from "../Workspace";
import { Assistant } from "./Assistant";
import { Inspector } from "./Inspector";
import { type SceneStatus } from "./Scene";
import { Timeline, sec } from "./Timeline";

const Scene = dynamic(() => import("./Scene"), {
  ssr: false,
  loading: () => <p className="p-4 text-[13px] text-muted">Loading the 3D view…</p>,
});

const MODE_TONE: Record<Mode, "accent" | "neutral" | "warn" | "unknown"> = {
  live: "accent",
  recorded: "neutral",
  simulated: "warn",
  disconnected: "unknown",
};

export function ModeBadge({ mode }: { mode: Mode }) {
  return (
    <span data-testid="mode" data-mode={mode}>
      <Badge tone={MODE_TONE[mode]}>{MODE_TEXT[mode]}</Badge>
    </span>
  );
}

export function TwinView() {
  return (
    <RequireIdentity>
      <Twin />
    </RequireIdentity>
  );
}

type Source = { kind: "recording" } | { kind: "observer"; env: string };

function Twin() {
  const { me, orgs, org, select } = useOrg();
  const params = useSearchParams();
  const router = useRouter();
  const devices = useDevices(org);
  const projects = useQuery({
    queryKey: ["projects", org],
    queryFn: () => api<Project[]>(`${orgPath(org!)}/projects`),
    enabled: !!org,
  });
  const project = params.get("project") ?? projects.data?.[0]?.slug ?? null;
  const base = org && project ? projectPath(org, project) : null;
  const recs = useQuery({
    queryKey: ["twin-recordings", org, project],
    queryFn: () => api<Recording[]>(`${base}/twin/recordings`),
    enabled: !!base,
  });
  const recId = params.get("recording") ?? recs.data?.[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["twin-recording", org, project, recId],
    queryFn: () => api<RecordingDetail>(`${base}/twin/recordings/${recId}`),
    enabled: !!base && !!recId,
  });
  const track = useQuery({
    queryKey: ["twin-track", org, project, recId, detail.data?.track_sha256],
    queryFn: () => api<Track>(`${base}/twin/recordings/${recId}/track`),
    enabled: !!base && !!recId && !!detail.data,
    staleTime: Infinity,
  });
  const models = useQuery({
    queryKey: ["twin-models", org, project],
    queryFn: () => api<{ slug: string; name: string; versions: { number: number }[] }[]>(`${base}/twin/models`),
    enabled: !!base,
  });
  const [source, setSource] = useState<Source>({ kind: "recording" });
  // The model: the recording's own when it names one, else the newest version of the first model in the project.
  const fallback = models.data?.[0] ? `${models.data[0].slug}@${models.data[0].versions.at(-1)?.number ?? 1}` : null;
  const modelRef = (source.kind === "recording" ? detail.data?.model : null) ?? detail.data?.model ?? fallback;
  const [mSlug, mNum] = modelRef ? modelRef.split("@") : [null, null];
  const version = useQuery({
    queryKey: ["twin-version", org, project, modelRef],
    queryFn: () => api<ModelVersion>(`${base}/twin/models/${mSlug}/versions/${mNum}`),
    enabled: !!base && !!mSlug && !!mNum,
  });
  const fileUrl = (p: string) => `${base}/twin/models/${mSlug}/versions/${mNum}/files/${p}`;
  const urdf = useQuery({
    queryKey: ["twin-urdf", org, project, modelRef, version.data?.manifest_sha256],
    queryFn: async () => new TextDecoder().decode(await apiBytes(fileUrl(version.data!.urdf_path))),
    enabled: !!version.data,
    staleTime: Infinity,
  });
  const structure = version.data?.structure as unknown as Structure | undefined;
  const meshFiles = useMemo(() => (version.data?.files ?? []).filter((f) => f.path.endsWith(".stl")).map((f) => f.path), [version.data]);
  const fetchFile = useCallback((p: string) => apiBytes(fileUrl(p)), [base, mSlug, mNum]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- playback (recorded) -------------------------------------------------------------------------------------
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const [eventId, setEventId] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const tr = track.data ?? null;
  // Baseline versus candidate: a second recording of the project, drawn as a ghost on the same time axis.
  const compareId = params.get("compare");
  const [align, setAlign] = useState<Align>("command_last");
  const detail2 = useQuery({
    queryKey: ["twin-recording", org, project, compareId],
    queryFn: () => api<RecordingDetail>(`${base}/twin/recordings/${compareId}`),
    enabled: !!base && !!compareId,
  });
  const track2 = useQuery({
    queryKey: ["twin-track", org, project, compareId, detail2.data?.track_sha256],
    queryFn: () => api<Track>(`${base}/twin/recordings/${compareId}/track`),
    enabled: !!base && !!compareId && !!detail2.data,
    staleTime: Infinity,
  });
  const tr2 = compareId ? (track2.data ?? null) : null;
  useEffect(() => {
    setT(0);
    setPlaying(false);
    setEventId(null);
  }, [recId]);
  const rateRef = useRef(rate);
  rateRef.current = rate;
  useEffect(() => {
    if (!playing || !tr) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      let ended = false;
      setT((prev) => {
        const nt = prev + dt * rateRef.current;
        if (nt >= tr.duration_s) {
          ended = true;
          return tr.duration_s;
        }
        return nt;
      });
      if (ended) setPlaying(false);
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, tr]);

  // ---- an observed robot (read-only) ---------------------------------------------------------------------------
  const observers = useMemo(() => {
    const byEnv = new Map<string, { graph?: Device; robot?: Device; kind: string }>();
    for (const d of devices.data ?? []) {
      if (!d.present || d.capabilities.some((c) => c.kind === "action")) continue;
      if (d.key !== "ros-graph" && d.key !== "ros-robot") continue;
      const e = byEnv.get(d.environment) ?? { kind: d.environment_kind };
      if (d.key === "ros-graph") e.graph = d;
      else e.robot = d;
      byEnv.set(d.environment, e);
    }
    return [...byEnv.entries()].filter(([, v]) => v.graph && v.robot).map(([env, v]) => ({ env, ...v }));
  }, [devices.data]);
  const obs = source.kind === "observer" ? observers.find((o) => o.env === source.env) : undefined;
  const wants: [string, Device | undefined, string][] = [
    ["connectivity", obs?.graph, "connectivity"],
    ["joint_states", obs?.robot, "joint_states"],
    ["transforms", obs?.robot, "transforms"],
  ];
  const reads = useQueries({
    queries: wants.map(([key, dev, prop]) => ({
      queryKey: ["twin-observe", org, dev?.id, key],
      queryFn: () => api<PropertyRead>(`${orgPath(org!)}/devices/${dev!.id}/properties/${prop}`),
      enabled: !!obs && !!dev,
      refetchInterval: 1000,
      retry: false,
    })),
  });
  const observed: ObserverReads = {
    connectivity: reads[0]?.data?.value as Record<string, unknown> | undefined,
    joint_states: reads[1]?.data?.value as Record<string, unknown> | undefined,
    transforms: reads[2]?.data?.value as Record<string, unknown> | undefined,
  };
  const observedFailed = reads.some((r) => r.isError);

  // ---- what is shown now ---------------------------------------------------------------------------------------
  const sample = useMemo(() => (source.kind === "recording" && tr ? sampleAt(tr, t) : null), [source.kind, tr, t]);
  let mode: Mode = "recorded";
  let modeReason = "Playing a recording: the model moves with the recorded /tf and /joint_states.";
  let pose: Pose | null = sample?.pose ?? null;
  let joints: Record<string, number> = sample ? jointValues(sample) : {};
  let reported: string[] = Object.keys(joints);
  if (source.kind === "observer") {
    const m = observerMode(obs?.kind ?? "simulated", observed, observedFailed || !obs);
    mode = m.mode;
    modeReason = m.reason;
    if (mode !== "disconnected") {
      joints = observerJoints(observed.joint_states);
      reported = Object.keys(joints);
      pose = observerBasePose(observed.transforms, tr?.frames.parent ?? "odom", structure?.root ?? "base_footprint");
    } else {
      joints = {};
      pose = null;
      reported = [];
    }
  }
  const alignedOffset = tr && tr2 ? compareOffset(tr, tr2, align) : null;
  const offset = alignedOffset ?? 0; // without the event in both recordings, they are aligned at their starts (said below)
  const ghostSample = source.kind === "recording" && tr2 ? sampleOther(tr2, t, offset) : null;
  const ghost = source.kind === "recording" && tr2 ? { pose: ghostSample?.pose ?? null, joints: ghostSample ? jointValues(ghostSample) : {} } : null;
  const gap = baseGap(pose, ghostSample?.pose ?? null);
  const modelJointNames = useMemo(() => (structure?.joints ?? []).filter((j) => j.type !== "fixed").map((j) => j.name), [structure]);
  const jointMatch = matchJoints(modelJointNames, reported);

  const frame = useMemo(() => {
    const b = tr?.base;
    if (!b || b.x.length === 0) return { cx: 0, cy: 0, radius: 1 };
    const minx = Math.min(...b.x);
    const maxx = Math.max(...b.x);
    const miny = Math.min(...b.y);
    const maxy = Math.max(...b.y);
    return { cx: (minx + maxx) / 2, cy: (miny + maxy) / 2, radius: Math.max((maxx - minx) / 2, (maxy - miny) / 2, 0.8) };
  }, [tr]);
  const [view, setView] = useState<"perspective" | "top">("perspective");
  const [viewNonce, setViewNonce] = useState(0);
  const [scene, setScene] = useState<SceneStatus>({ state: "loading" });

  const events = (tr?.events ?? []) as TwinEvent[];
  const event = events.find((e) => e.id === eventId) ?? null;
  const pick = (e: TwinEvent) => {
    setPlaying(false);
    setEventId(e.id);
    setT(e.t);
  };
  const setParam = (k: string, v: string) => {
    const q = new URLSearchParams(params.toString());
    q.set(k, v);
    if (org) q.set("org", org);
    router.replace(`/twin?${q.toString()}`);
  };

  if (me.isLoading || projects.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  if (!org) return <Notice tone="info">You have no workspace yet. <Link className="underline" href="/onboarding">Get started</Link>.</Notice>;
  if (!project) return <Notice tone="info">This workspace has no project. Create one under Release intelligence first.</Notice>;

  const d = detail.data;
  const ident = d?.identity as { software?: { commit?: string; tree_dirty?: boolean } } | null | undefined;
  const sw = ident?.software;
  const empty = recs.data && recs.data.length === 0 && observers.length === 0;

  const left = (
    <div className="flex h-full flex-col overflow-auto">
      <section aria-labelledby="src-h" className="border-b border-line p-3">
        <h2 id="src-h" className="mb-2 text-[12px] font-medium text-faint">
          Source
        </h2>
        <ul className="space-y-1">
          {(recs.data ?? []).map((r) => (
            <li key={r.id}>
              <button
                className={clsx("w-full rounded-sm border px-2 py-1.5 text-left text-[12px]", source.kind === "recording" && r.id === recId ? "border-accent bg-sunken" : "border-line hover:bg-sunken")}
                aria-pressed={source.kind === "recording" && r.id === recId}
                onClick={() => {
                  setSource({ kind: "recording" });
                  setParam("recording", r.id);
                }}
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium">{r.label}</span>
                  <Badge tone="neutral">recording</Badge>
                </div>
                <div className="num mt-0.5 text-faint">
                  {r.duration_s.toFixed(1)} s · {r.clock} clock{r.model ? ` · ${r.model}` : ""}
                </div>
                {r.episode && (
                  <div className="mt-1 flex items-center gap-1.5">
                    <ClassBadge value={r.episode.outcome_class} />
                    <span className="num text-faint">{r.episode.release_label}</span>
                  </div>
                )}
              </button>
            </li>
          ))}
          {source.kind === "recording" && (recs.data ?? []).length > 1 && (
            <li className="pt-2">
              <label className="block text-[12px] text-muted">
                Compare with (drawn as a ghost)
                <select className="field mt-1 w-full py-1" value={compareId ?? ""} onChange={(e) => setParam("compare", e.target.value)}>
                  <option value="">No comparison</option>
                  {(recs.data ?? [])
                    .filter((r) => r.id !== recId)
                    .map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.label}
                      </option>
                    ))}
                </select>
              </label>
              {compareId && (
                <label className="mt-1 block text-[12px] text-muted">
                  Align the two recordings at
                  <select className="field mt-1 w-full py-1" value={align} onChange={(e) => setAlign(e.target.value as Align)}>
                    <option value="command_last">the last command each received</option>
                    <option value="start">their starts</option>
                  </select>
                </label>
              )}
            </li>
          )}
          {observers.map((o) => (
            <li key={o.env}>
              <button
                className={clsx("w-full rounded-sm border px-2 py-1.5 text-left text-[12px]", source.kind === "observer" && source.env === o.env ? "border-accent bg-sunken" : "border-line hover:bg-sunken")}
                aria-pressed={source.kind === "observer" && source.env === o.env}
                onClick={() => {
                  setSource({ kind: "observer", env: o.env });
                  setPlaying(false);
                }}
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium">{o.env}</span>
                  <Badge tone="neutral">observer</Badge>
                </div>
                <div className="mt-0.5 text-faint">Read-only view of a ROS 2 graph</div>
              </button>
            </li>
          ))}
        </ul>
        {empty && (
          <p className="mt-2 text-[12px] text-muted">
            This project has no recording and no observed robot. Import a recording with <span className="num">scripts/import_twin.py</span>, or connect an observer
            under <Link className="underline" href={`/hardware?org=${org}`}>Hardware Hub</Link>.
          </p>
        )}
      </section>
      <section aria-labelledby="ev-h" className="p-3">
        <h2 id="ev-h" className="mb-2 text-[12px] font-medium text-faint">
          Events in the recording
        </h2>
        {source.kind === "observer" && <p className="text-[12px] text-muted">An observed graph has no recorded events.</p>}
        {source.kind === "recording" && events.length === 0 && <p className="text-[12px] text-muted">None found by the rules.</p>}
        <ol className="space-y-1">
          {(source.kind === "recording" ? events : []).map((e) => (
            <li key={e.id}>
              <button
                className={clsx("w-full rounded-sm border px-2 py-1.5 text-left text-[12px]", e.id === eventId ? "border-accent bg-sunken" : "border-line hover:bg-sunken")}
                aria-pressed={e.id === eventId}
                onClick={() => pick(e)}
                data-event-kind={e.kind}
              >
                <div className="flex items-center gap-2">
                  <Badge tone={e.severity === "problem" ? "bad" : e.severity === "warning" ? "warn" : "neutral"}>{e.severity}</Badge>
                  <span className="num text-faint">{sec(e.t)}</span>
                </div>
                <div className="mt-0.5">{e.title}</div>
              </button>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );

  const center = (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-3 py-1.5 text-[12px]">
        <ModeBadge mode={mode} />
        <span className="text-muted" data-testid="mode-reason">{modeReason}</span>
        {source.kind === "recording" && compareId && detail2.data && (
          <span className="flex w-full flex-wrap items-center gap-x-2 gap-y-1 border-t border-line pt-1" data-testid="comparison">
            <span>
              <span className="text-muted">Solid: </span>
              <span className="font-medium">{d?.label}</span>{" "}
            </span>
            {d?.run?.verdict && <VerdictBadge verdict={d.run.verdict} />}
            <span>
              <span className="text-muted"> · Ghost: </span>
              <span className="font-medium">{detail2.data.label}</span>{" "}
            </span>
            {detail2.data.run?.verdict && <VerdictBadge verdict={detail2.data.run.verdict} />}
            <span className="text-muted">
              {" "}· aligned at {align === "start" || alignedOffset === null ? "their starts" : "the last command"}
              {align === "command_last" && alignedOffset === null ? " (one recording has no last-command event)" : ""}{" "}
            </span>
            <span className="num" data-testid="base-gap">
              {ghostSample ? (gap !== null ? `· bases ${gap.toFixed(2)} m apart now ` : "") : "· the ghost recording has no data at this moment "}
            </span>
            <button className="ml-auto text-accent hover:underline" onClick={() => setParam("compare", "")}>
              Stop comparing
            </button>
          </span>
        )}
        {source.kind === "recording" && d?.run && (
          <span className="ml-auto flex flex-wrap items-center gap-x-2 gap-y-1" data-testid="trial-link">
            <span className="text-muted">
              Trial {d.run.arm ?? "run"}
              {d.run.seed !== null && d.run.seed !== undefined ? ` · seed ${d.run.seed}` : ""}
            </span>
            <span className="text-muted">Engine verdict</span>
            <VerdictBadge verdict={d.run.verdict} />
            <Badge tone="warn">SIMULATED EVIDENCE</Badge>
            {d.run.experiment && d.run.request_id && (
              <Link className="text-accent hover:underline" href={`/experiments?org=${org}&exp=${d.run.experiment}&request=${d.run.request_id}`}>
                {d.run.experiment_name} v{d.run.version}: all trials
              </Link>
            )}
          </span>
        )}
        {source.kind === "recording" && d?.episode && (
          <span className="ml-auto flex items-center gap-2">
            <span className="text-muted">Engine verdict</span>
            <ClassBadge value={d.episode.outcome_class} />
            <Link className="text-accent hover:underline" href={`/o/${org}/p/${project}/e/${d.episode.evaluation_id}/episodes?episode=${d.episode.id}`}>
              Episode {d.episode.episode_key}
            </Link>
          </span>
        )}
      </div>
      {mode === "disconnected" && (
        <div className="px-3 pt-2">
          <Notice tone="warn">Disconnected: nothing is being received, so the model is not moving. It shows the neutral pose, not the robot&apos;s last position.</Notice>
        </div>
      )}
      {source.kind === "observer" && mode !== "disconnected" && (
        <div className="px-3 pt-2">
          <Notice tone="info">
            {jointMatch.matched.length} of {reported.length} reported joints exist in this model
            {jointMatch.unmatched.length > 0 ? `; ${jointMatch.unmatched.length} are not in it and are not drawn` : ""}.
            {pose ? " Base pose from TF." : " No TF for the base frame was seen, so the base is drawn at the origin."}
          </Notice>
        </div>
      )}
      <div className="relative min-h-[240px] flex-1">
        {urdf.data && version.data && structure ? (
          <div role="img" aria-label="3D view of the robot model. The same information is listed as text below the view." className="absolute inset-0">
            <Scene
              urdf={urdf.data}
              files={meshFiles}
              fetchFile={fetchFile}
              pose={pose}
              joints={joints}
              selected={link}
              onSelect={setLink}
              onStatus={setScene}
              frame={frame}
              view={view}
              viewNonce={viewNonce}
              ghost={ghost}
            />
          </div>
        ) : (
          <p className="p-4 text-[13px] text-muted">
            {version.isError || urdf.isError ? "The robot model could not be loaded." : modelRef ? "Loading the model…" : "No robot model is registered in this project, so there is nothing to draw. The data below is still shown."}
          </p>
        )}
        <div className="absolute bottom-2 left-2 flex gap-1.5">
          <button className="btn" onClick={() => setViewNonce((n) => n + 1)}>
            <RotateCcw size={13} aria-hidden /> Reset view
          </button>
          <button className="btn" aria-pressed={view === "top"} onClick={() => setView((v) => (v === "top" ? "perspective" : "top"))}>
            <Eye size={13} aria-hidden /> {view === "top" ? "Perspective view" : "Top view"}
          </button>
        </div>
        {scene.state === "error" && <div className="absolute right-2 top-2 max-w-xs"><Notice tone="bad">3D view: {scene.message}</Notice></div>}
        {scene.state === "ready" && <span className="sr-only" data-testid="scene-ready" data-meshes={scene.meshes} />}
      </div>
      <dl className="num flex flex-wrap gap-x-5 gap-y-0.5 border-t border-line px-3 py-1.5 text-[12px]" data-testid="readout" aria-label="Text equivalent of the 3D view">
        <div className="flex gap-1.5">
          <dt className="text-muted">{source.kind === "recording" ? "Time" : "Source"}</dt>
          <dd>{source.kind === "recording" ? `${sec(t)} on the ${tr?.clock === "sim" ? "simulation" : "log"} clock` : `${source.env} (${modeReason})`}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-muted">Base pose</dt>
          <dd data-testid="pose">{pose ? `x ${pose.x.toFixed(3)} m, y ${pose.y.toFixed(3)} m, yaw ${pose.yaw.toFixed(3)} rad` : "no pose"}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-muted">Joints</dt>
          <dd>{Object.keys(joints).length ? Object.entries(joints).map(([k, v]) => `${k} ${v.toFixed(3)} rad`).join(", ") : "no joint values"}</dd>
        </div>
        {sample && (
          <div className="flex gap-1.5">
            <dt className="text-muted">Commands</dt>
            <dd>{Object.entries(sample.commands).map(([k, v]) => `${k} ${v ? `${v.linear_x.toFixed(2)} m/s` : "none yet"}`).join(", ") || "none recorded"}</dd>
          </div>
        )}
      </dl>
    </div>
  );

  return (
    <div className="-mx-4 -my-5 flex h-[calc(100vh-44px)] min-h-[640px] flex-col md:-mx-7">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5 md:px-7">
        <h1 className="text-[15px] font-semibold">Digital twin</h1>
        {(projects.data?.length ?? 0) > 1 && (
          <label className="flex items-center gap-2 text-[12px] text-muted">
            Project
            <select className="field py-1" value={project} onChange={(e) => setParam("project", e.target.value)}>
              {projects.data?.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {version.data && (
          <span className="num text-[12px] text-muted" title={`manifest ${version.data.manifest_sha256}`}>
            {version.data.model_name} v{version.data.number} · {(version.data.source as { repository?: string; commit?: string; license_spdx?: string }).repository}@
            {String((version.data.source as { commit?: string }).commit).slice(0, 10)} · {(version.data.source as { license_spdx?: string }).license_spdx}
          </span>
        )}
        {sw && source.kind === "recording" && (
          <span className="num text-[12px] text-muted">
            run on {String(sw.commit).slice(0, 10)} {sw.tree_dirty ? <Badge tone="warn">modified tree</Badge> : <Badge tone="neutral">clean tree</Badge>}
          </span>
        )}
        <div className="ml-auto flex items-center gap-3">
          <Link className="text-[12px] text-accent hover:underline" href={`/workbench?org=${org}`}>
            Workbench runs
          </Link>
          <OrgSelect orgs={orgs} org={org} select={select} />
        </div>
      </div>
      {recs.isError && <div className="px-4 pt-2"><Notice tone="bad">Could not read recordings: {recs.error.message}</Notice></div>}
      {source.kind === "recording" && recId && track.isError && <div className="px-4 pt-2"><Notice tone="bad">The recording could not be read: {track.error.message}</Notice></div>}
      <Split
        side="bottom"
        label="Resize the timeline"
        initial={200}
        min={110}
        max={420}
        className="flex-1"
        pane={
          source.kind === "recording" && tr && sample ? (
            <Timeline track={tr} sample={sample} t={t} playing={playing} rate={rate} selectedEvent={eventId} onSeek={(v) => { setPlaying(false); setT(v); }} onPlay={setPlaying} onRate={setRate} onSelectEvent={pick} />
          ) : (
            <p className="p-3 text-[13px] text-muted">
              {source.kind === "observer" ? "An observed graph is not a recording: there is no timeline to play, only the latest values, read once a second." : "Pick a recording to play."}
            </p>
          )
        }
      >
        <Split side="start" label="Resize the sources panel" initial={260} min={200} max={420} className="h-full" pane={left}>
          <Split
            side="end"
            label="Resize the inspector"
            initial={360}
            min={280}
            max={560}
            className="h-full"
            pane={
              <div className="flex h-full flex-col overflow-auto">
                {structure ? (
                  <Inspector structure={structure} sample={sample} track={tr} selected={link} onSelect={setLink} modelName={`${version.data?.model_name ?? ""} v${version.data?.number ?? ""}`} />
                ) : (
                  <p className="p-3 text-[12px] text-muted">The model has not loaded.</p>
                )}
                {source.kind === "recording" && recId && <Assistant org={org} project={project} recordingId={recId} event={event} />}
              </div>
            }
          >
            {center}
          </Split>
        </Split>
      </Split>
    </div>
  );
}
