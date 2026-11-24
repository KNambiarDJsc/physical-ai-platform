"use client";

/**
 * Fleet, Incidents, Verification, Evidence and Integrations. Each page is a view over data the platform already
 * holds (evaluations, episodes, engine incidents, artifacts, credentials). Nothing here is computed, estimated or
 * invented: counts are counts of stored rows, verdicts are the engine's, and an empty state says what is missing.
 */

import { useQueries } from "@tanstack/react-query";
import Link from "next/link";
import { api, projectPath, type Artifact, type Evaluation, type EpisodePage, type Project } from "@/lib/api/client";
import { shortDigest } from "@/lib/format";
import { Notice, PageHeader, Panel } from "./AppShell";
import { RequireIdentity, useAuth, useMe } from "./Identity";
import { Badge, ClassBadge, StateBadge, Table, Td, Time, VerdictBadge } from "./ui";

type Workspace = {
  org: string;
  role: string;
  project: Project;
  evaluations: Evaluation[];
  artifacts: Artifact[];
  latest: Evaluation | undefined;
};

/** Every project the caller can see, with its evaluations and artifacts. */
function useWorkspace() {
  const me = useMe();
  const orgs = me.data?.organizations ?? [];
  const projects = useQueries({
    queries: orgs.map((o) => ({ queryKey: ["projects", o.slug], queryFn: () => api<Project[]>(`/api/v1/orgs/${o.slug}/projects`) })),
  });
  const flat = orgs.flatMap((o, i) => (projects[i]?.data ?? []).map((p) => ({ org: o.slug, role: o.role, project: p })));
  const evals = useQueries({
    queries: flat.map((w) => ({
      queryKey: ["evaluations", w.org, w.project.slug],
      queryFn: () => api<Evaluation[]>(`${projectPath(w.org, w.project.slug)}/evaluations`),
    })),
  });
  const arts = useQueries({
    queries: flat.map((w) => ({
      queryKey: ["artifacts", w.org, w.project.slug],
      queryFn: () => api<Artifact[]>(`${projectPath(w.org, w.project.slug)}/artifacts`),
    })),
  });
  const items: Workspace[] = flat.map((w, i) => {
    const evaluations = [...(evals[i]?.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));
    return { ...w, evaluations, artifacts: arts[i]?.data ?? [], latest: evaluations.find((e) => e.state === "succeeded") };
  });
  const loading = me.isLoading || projects.some((q) => q.isLoading) || evals.some((q) => q.isLoading) || arts.some((q) => q.isLoading);
  const error = me.error ?? projects.find((q) => q.error)?.error ?? evals.find((q) => q.error)?.error ?? arts.find((q) => q.error)?.error;
  return { items, orgs, loading, error: error as Error | null | undefined };
}

function Shell({ title, subtitle, children }: { title: string; subtitle: string; children: (w: ReturnType<typeof useWorkspace>) => React.ReactNode }) {
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      <RequireIdentity>
        <Body>{children}</Body>
      </RequireIdentity>
    </>
  );
}

function Body({ children }: { children: (w: ReturnType<typeof useWorkspace>) => React.ReactNode }) {
  const w = useWorkspace();
  if (w.loading) return <p className="text-[13px] text-muted">Loading…</p>;
  if (w.error) return <Notice tone="bad">Could not reach the API: {w.error.message}</Notice>;
  if (w.items.length === 0)
    return (
      <Notice tone="info">
        No projects yet. Create one on the <Link className="underline" href="/">Overview</Link> and run an evaluation; this page fills from it.
      </Notice>
    );
  return <div className="space-y-4">{children(w)}</div>;
}

const kib = (n: number) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MiB` : `${(n / 1024).toFixed(1)} KiB`);
const evalHref = (w: Workspace, e: Evaluation) => `/o/${w.org}/p/${w.project.slug}/e/${e.id}`;
const summary = (e: Evaluation) =>
  (e.summary ?? {}) as { classes?: Record<string, Record<string, number>>; episodes?: number; rejected_rows?: number; verdict_reported?: string; verdict_verified?: string };
const evidenceClass = (e: Evaluation | undefined) => ((e?.provenance ?? {}) as { evidence_class?: string[] }).evidence_class ?? [];

// ---------------------------------------------------------------------------------------------------- Verification

export function VerificationView() {
  return (
    <Shell
      title="Verification"
      subtitle="Does what the robot reported agree with what was independently measured? One row per evaluation, verdicts from the engine."
    >
      {({ items }) => {
        const rows = items.flatMap((w) => w.evaluations.map((e) => ({ w, e })));
        return (
          <>
            <Panel title="Reported vs independently verified">
              {rows.length === 0 ? (
                <p className="text-[13px] text-muted">No evaluations yet.</p>
              ) : (
                <Table head={["Comparison", "Robot reported", "Independently verified", "Agree", "Episodes", "Contradictions", "Evidence", "Run"]}>
                  {rows.map(({ w, e }) => {
                    const s = summary(e);
                    const done = e.state === "succeeded";
                    const contradictions = Object.values(s.classes ?? {}).reduce((n, c) => n + (c.contradiction ?? 0), 0);
                    return (
                      <tr key={e.id}>
                        <Td className="min-w-[14rem] whitespace-normal">
                          <Link className="font-medium text-accent hover:underline" href={evalHref(w, e)}>
                            {e.baseline_label} → {e.candidate_label}
                          </Link>
                          <div className="text-xs text-muted">
                            {w.project.name}
                            {!done && <> · <StateBadge state={e.state} /></>}
                          </div>
                        </Td>
                        <Td>{done && s.verdict_reported ? <VerdictBadge verdict={s.verdict_reported} /> : "—"}</Td>
                        <Td>{done && s.verdict_verified ? <VerdictBadge verdict={s.verdict_verified} /> : "—"}</Td>
                        <Td>
                          {done && s.verdict_reported && s.verdict_verified ? (
                            s.verdict_reported === s.verdict_verified ? <Badge tone="ok">same</Badge> : <Badge tone="warn">differs</Badge>
                          ) : "—"}
                        </Td>
                        <Td num>{done ? (s.episodes ?? "—") : "—"}</Td>
                        <Td num>{done ? contradictions : "—"}</Td>
                        <Td>{done ? evidenceClass(e).join(", ") || "—" : "—"}</Td>
                        <Td>
                          <Time iso={e.created_at} />
                        </Td>
                      </tr>
                    );
                  })}
                </Table>
              )}
            </Panel>
            <p className="max-w-3xl text-xs text-muted">
              A contradiction is an episode where the robot&apos;s report and the independent measurement disagree. Verdicts &quot;same&quot; or
              &quot;differs&quot; only compare the two engine verdicts of one evaluation; open it for the intervals behind each.
            </p>
          </>
        );
      }}
    </Shell>
  );
}

// ---------------------------------------------------------------------------------------------------------- Evidence

export function EvidenceView() {
  return (
    <Shell
      title="Evidence"
      subtitle="Every file stored for your projects: what you uploaded and what the engine produced from it. Content-addressed and write-once."
    >
      {({ items }) => (
        <>
          {items.map((w) => {
            const used = (id: string) => w.evaluations.filter((e) => Object.values(e.artifacts).some((ids) => ids.includes(id))).length;
            return (
              <Panel key={`${w.org}/${w.project.slug}`} title={`${w.project.name} · ${w.artifacts.length} files`}>
                {w.artifacts.length === 0 ? (
                  <p className="text-[13px] text-muted">No evidence uploaded yet.</p>
                ) : (
                  <Table head={["File", "Kind", "Size", "SHA-256", "Used in", "Stored", "By"]}>
                    {w.artifacts.map((a) => (
                      <tr key={a.id}>
                        <Td className="font-medium">{a.filename}</Td>
                        <Td><Badge tone={a.created_by === "worker" ? "neutral" : "accent"}>{a.created_by === "worker" ? `${a.kind} (engine output)` : a.kind}</Badge></Td>
                        <Td num>{kib(a.size_bytes)}</Td>
                        <Td className="num" >{shortDigest(a.sha256)}</Td>
                        <Td num>{used(a.id) ? `${used(a.id)} evaluation${used(a.id) === 1 ? "" : "s"}` : "—"}</Td>
                        <Td><Time iso={a.created_at} /></Td>
                        <Td>{a.created_by === "worker" ? "worker" : "you"}</Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Panel>
            );
          })}
          <p className="max-w-3xl text-xs text-muted">
            The SHA-256 is of the stored bytes. The same digest appears in every report that used the file, so a result can be traced back to the
            exact input.
          </p>
        </>
      )}
    </Shell>
  );
}

// ------------------------------------------------------------------------------------------------------------ Fleet

type EpisodeRow = EpisodePage["items"][number];

async function allEpisodes(base: string, id: string): Promise<{ items: EpisodeRow[]; total: number }> {
  const items: EpisodeRow[] = [];
  let total = 0;
  for (let offset = 0; offset < 2000; offset += 500) {
    const page = await api<EpisodePage>(`${base}/evaluations/${id}/episodes?limit=500&offset=${offset}`);
    total = page.total;
    items.push(...page.items);
    if (items.length >= total) break;
  }
  return { items, total };
}

export function FleetView() {
  return (
    <Shell title="Fleet" subtitle="Every robot that appears in your evidence, with its outcome counts, from the latest finished evaluation of each project.">
      {({ items }) => <Fleet items={items} />}
    </Shell>
  );
}

function Fleet({ items }: { items: Workspace[] }) {
  const withEval = items.filter((w) => w.latest);
  const eps = useQueries({
    queries: withEval.map((w) => ({
      queryKey: ["fleet", w.org, w.project.slug, w.latest!.id],
      queryFn: () => allEpisodes(projectPath(w.org, w.project.slug), w.latest!.id),
    })),
  });
  if (withEval.length === 0) return <Notice tone="info">No finished evaluations yet. Robots appear here once evidence has been evaluated.</Notice>;
  return (
    <>
      {withEval.map((w, i) => {
        const q = eps[i];
        const rows = new Map<string, { robot: string; site: string; release: string; n: number; c: Record<string, number> }>();
        const labels = new Map([[w.latest!.baseline_release_id, w.latest!.baseline_label], [w.latest!.candidate_release_id, w.latest!.candidate_label]]);
        for (const e of q?.data?.items ?? []) {
          const key = `${e.robot}|${e.site ?? ""}|${e.release_id}`;
          const r = rows.get(key) ?? { robot: e.robot, site: e.site ?? "—", release: labels.get(e.release_id) ?? shortDigest(e.release_id), n: 0, c: {} };
          r.n += 1;
          r.c[e.outcome_class] = (r.c[e.outcome_class] ?? 0) + 1;
          rows.set(key, r);
        }
        const robots = new Set([...rows.values()].map((r) => r.robot));
        return (
          <Panel key={`${w.org}/${w.project.slug}`} title={`${w.project.name} · ${q?.data ? `${robots.size} robot${robots.size === 1 ? "" : "s"}, ${q.data.total} episodes` : "loading"}`}>
            {q?.isLoading && <p className="text-[13px] text-muted">Loading episodes…</p>}
            {q?.error && <Notice tone="bad">{q.error.message}</Notice>}
            {q?.data && (
              <Table head={["Robot", "Site", "Release", "Episodes", "Supported success", "Verified success", "Verified failure", "Contradiction", "Unknown / other"]}>
                {[...rows.values()].map((r) => {
                  const known = ["supported_success", "verified_success", "verified_failure", "contradiction"];
                  const other = Object.entries(r.c).filter(([k]) => !known.includes(k)).reduce((n, [, v]) => n + v, 0);
                  return (
                    <tr key={`${r.robot}|${r.site}|${r.release}`}>
                      <Td className="font-medium">{r.robot}</Td>
                      <Td>{r.site}</Td>
                      <Td>{r.release}</Td>
                      <Td num>{r.n}</Td>
                      <Td num>{r.c.supported_success ?? 0}</Td>
                      <Td num>{r.c.verified_success ?? 0}</Td>
                      <Td num>{r.c.verified_failure ?? 0}</Td>
                      <Td num>{r.c.contradiction ?? 0}</Td>
                      <Td num>{other}</Td>
                    </tr>
                  );
                })}
              </Table>
            )}
            <p className="mt-2 text-xs text-muted">
              From evaluation <Link className="underline" href={evalHref(w, w.latest!)}>{w.latest!.baseline_label} → {w.latest!.candidate_label}</Link>.
              Counts of episodes, not rates; reliability claims live in the evaluation&apos;s verdicts.
              {q?.data && q.data.items.length < q.data.total ? ` Showing the first ${q.data.items.length} of ${q.data.total} episodes.` : ""}
            </p>
          </Panel>
        );
      })}
    </>
  );
}

// ------------------------------------------------------------------------------------------------------- Incidents

type Incident = {
  incident_id: string;
  status: string;
  robot: string;
  site?: string | null;
  release: string;
  task_id: string;
  headline: string;
  reported: string;
  verified: string;
  triggers: string[];
  members: number;
  opened_ns: number;
};

export function IncidentsView() {
  return (
    <Shell
      title="Incidents"
      subtitle="Failures the engine grouped into incidents (a task the robot timed out on, or one the measurement shows violated), from the latest finished evaluation of each project."
    >
      {({ items }) => <Incidents items={items} />}
    </Shell>
  );
}

function Incidents({ items }: { items: Workspace[] }) {
  const withEval = items.filter((w) => w.latest);
  const qs = useQueries({
    queries: withEval.map((w) => ({
      queryKey: ["incidents", w.org, w.project.slug, w.latest!.id],
      queryFn: () => api<Incident[]>(`${projectPath(w.org, w.project.slug)}/evaluations/${w.latest!.id}/incidents`),
    })),
  });
  if (withEval.length === 0) return <Notice tone="info">No finished evaluations yet. Incidents appear here once evidence has been evaluated.</Notice>;
  const SHOW = 12;
  const ENGINE_LIMIT = 50; // the engine's `ops incidents` default limit (newest first); more may exist
  return (
    <>
      {withEval.map((w, i) => {
        const q = qs[i];
        const list = q?.data ?? [];
        return (
          <Panel key={`${w.org}/${w.project.slug}`} title={`${w.project.name} · ${q?.data ? (list.length >= ENGINE_LIMIT ? `the newest ${ENGINE_LIMIT} incidents` : `${list.length} incident${list.length === 1 ? "" : "s"}`) : "loading"}`}>
            {q?.isLoading && <p className="text-[13px] text-muted">Loading…</p>}
            {q?.error && <Notice tone="bad">{q.error.message}</Notice>}
            {q?.data && list.length === 0 && <p className="text-[13px] text-muted">The engine found no incidents in this evaluation.</p>}
            {list.length > 0 && (
              <Table head={["Incident", "Robot", "Release", "Reported", "Verified", "What the engine found"]}>
                {list.slice(0, SHOW).map((x) => (
                  <tr key={x.incident_id}>
                    <Td className="num">{x.incident_id}</Td>
                    <Td>{x.robot}</Td>
                    <Td>{x.release}</Td>
                    <Td>{x.reported === "unknown" ? <Badge tone="unknown">unknown</Badge> : x.reported}</Td>
                    <Td>
                      {x.verified === "violated" ? (
                        <ClassBadge value="verified_failure" />
                      ) : x.verified === "satisfied" ? (
                        <Badge tone="ok">satisfied</Badge>
                      ) : (
                        x.verified
                      )}
                    </Td>
                    <td className="min-w-[20rem] px-2 py-1.5 text-xs leading-snug text-muted">{x.headline}</td>
                  </tr>
                ))}
              </Table>
            )}
            <p className="mt-2 text-xs text-muted">
              From evaluation <Link className="underline" href={evalHref(w, w.latest!)}>{w.latest!.baseline_label} → {w.latest!.candidate_label}</Link>.
              {list.length > SHOW ? ` Showing the first ${SHOW} of the ${list.length} the engine returned.` : ""}{list.length >= ENGINE_LIMIT ? ` The engine lists at most ${ENGINE_LIMIT} (newest first), so more incidents may exist than are shown.` : ""} The engine writes the explanation; the platform only lists it.
            </p>
          </Panel>
        );
      })}
    </>
  );
}

// ---------------------------------------------------------------------------------------------------- Integrations

type Credential = { id: string; name: string; role: string; token_prefix: string; created_at: string; last_used_at: string | null; revoked_at: string | null };

export function IntegrationsView() {
  return (
    <Shell title="Integrations" subtitle="How other systems feed this platform and read from it: the API, machine credentials, sign-in and the evaluation engine.">
      {({ items, orgs }) => <Integrations items={items} orgs={orgs} />}
    </Shell>
  );
}

function Integrations({ items, orgs }: { items: Workspace[]; orgs: { slug: string; role: string }[] }) {
  const auth = useAuth();
  const admin = orgs.filter((o) => o.role === "admin");
  const creds = useQueries({
    queries: admin.map((o) => ({ queryKey: ["credentials", o.slug], queryFn: () => api<Credential[]>(`/api/v1/orgs/${o.slug}/service-credentials`) })),
  });
  const eng = ((items.find((w) => w.latest)?.latest?.provenance ?? {}) as { engine?: Record<string, string> }).engine ?? {};
  const first = items[0];
  const base = first ? `/api/v1/orgs/${first.org}/projects/${first.project.slug}` : "/api/v1/orgs/{org}/projects/{project}";
  const a = auth.data;
  return (
    <>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Sign-in">
          <dl className="space-y-1 text-[13px]">
            <Row k="Mode" v={a ? (a.mode === "oidc" ? "OpenID Connect (code + PKCE)" : a.mode === "dev" ? "Development identity (this machine only)" : "Misconfigured") : "—"} />
            <Row k="Signed in as" v={a?.mode === "oidc" ? (a.user?.name ?? "—") : (orgs.length ? "your development identity" : "—")} />
          </dl>
          <p className="mt-2 text-xs text-muted">Production installs refuse the development identity; browsers never hold the access token.</p>
        </Panel>
        <Panel title="Evaluation engine">
          <dl className="space-y-1 text-[13px]">
            <Row k="Engine" v={eng.version ?? "—"} />
            <Row k="Commit" v={eng.commit ? eng.commit.slice(0, 12) : "—"} />
            <Row k="Binary" v={shortDigest(eng.binary_sha256)} />
          </dl>
          <p className="mt-2 text-xs text-muted">Read from the latest finished evaluation. The platform calls this pinned build; it never reimplements its statistics.</p>
        </Panel>
      </div>
      <Panel title="Execution environments">
        <p className="text-sm text-muted">Inspect the operator catalog, discover instrument capabilities and read device health in Hardware Hub.</p>
        <ul className="mt-2 space-y-1">{orgs.map((o) => <li key={o.slug}><Link className="text-accent underline" href={{ pathname: "/hardware", query: { org: o.slug } }}>Open {o.slug} environments</Link></li>)}</ul>
      </Panel>
      <Panel title="Machine credentials (CI and robots posting evidence)">
        {admin.length === 0 && <p className="text-[13px] text-muted">Only organization admins can see credentials.</p>}
        {admin.map((o, i) => {
          const q = creds[i];
          return (
            <div key={o.slug} className="mb-3">
              <div className="mb-1 text-xs font-medium text-muted">{o.slug}</div>
              {q?.error && <Notice tone="bad">{q.error.message}</Notice>}
              {q?.data && q.data.length === 0 && <p className="text-[13px] text-muted">No machine credentials. Create one through the API (below); the token is shown once.</p>}
              {q?.data && q.data.length > 0 && (
                <Table head={["Name", "Role", "Prefix", "Created", "Last used", "State"]}>
                  {q.data.map((c) => (
                    <tr key={c.id}>
                      <Td className="font-medium">{c.name}</Td>
                      <Td>{c.role}</Td>
                      <Td className="num">{c.token_prefix}…</Td>
                      <Td><Time iso={c.created_at} /></Td>
                      <Td><Time iso={c.last_used_at} /></Td>
                      <Td>{c.revoked_at ? <Badge tone="neutral">revoked</Badge> : <Badge tone="ok">active</Badge>}</Td>
                    </tr>
                  ))}
                </Table>
              )}
            </div>
          );
        })}
      </Panel>
      <Panel title="The API">
        <p className="mb-2 text-[13px] text-muted">
          Everything on these pages is the same API your pipelines can call (HTTPS, JSON, <span className="num">Authorization: Bearer &lt;token&gt;</span>). Interactive
          reference: <span className="num">/api/docs</span> on the API server (development installs).
        </p>
        <Table head={["Do this", "Request"]}>
          {[
            ["Register a release", `POST ${base}/releases`],
            ["Upload evidence (CSV)", `POST ${base}/artifacts`],
            ["Add a mapping version", `POST ${base}/mappings`],
            ["Start an evaluation", `POST ${base}/evaluations`],
            ["Fetch the comparison", `GET  ${base}/evaluations/{id}/comparison`],
            ["Download the report", `GET  ${base}/evaluations/{id}/report.json  |  report.html`],
            ["Create a machine credential", `POST /api/v1/orgs/{org}/service-credentials`],
            ["Metrics for Prometheus", `GET  /metrics (API server)`],
          ].map(([k, v]) => (
            <tr key={k}>
              <Td>{k}</Td>
              <Td className="num">{v}</Td>
            </tr>
          ))}
        </Table>
      </Panel>
      <Panel title="Not integrated yet">
        <p className="text-[13px] text-muted">
          Direct connectors (ROS 2 bags, fleet managers, ticketing) are not built. Evidence arrives as CSV through the API today. Adding a connector
          means writing a mapping and a small exporter; nothing on this page implies one exists.
        </p>
      </Panel>
    </>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-28 shrink-0 text-muted">{k}</dt>
      <dd className="num">{v}</dd>
    </div>
  );
}
