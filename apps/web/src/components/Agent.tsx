"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { api, orgPath, type Proposal } from "@/lib/api/client";
import { shortDigest } from "@/lib/format";
import { Notice, PageHeader, Panel } from "./AppShell";
import { RequireIdentity } from "./Identity";
import { Markdown } from "./Markdown";
import { Badge, Time } from "./ui";
import { OrgSelect, useOrg } from "./Workspace";

type Status = {
  runner_available: boolean;
  model_configured: boolean;
  model: string | null;
  priced: boolean;
  role: string;
  can_ask: boolean;
  session_usd_cap: number;
  daily_usd_cap: number;
  daily_sessions_cap: number;
  sessions_today: number;
  usd_today: number;
  max_steps: number;
  timeout_s: number;
};
type Usage = { model_calls: number; input_tokens: number; output_tokens: number; usd: number | null; priced: boolean };
type Step = {
  n: number;
  kind: "tool" | "model";
  tool?: string;
  input?: unknown;
  permitted?: boolean;
  output?: unknown;
  output_sha256?: string | null;
  error?: string | null;
  input_tokens?: number;
  output_tokens?: number;
  t: number;
};
type Session = {
  id: string;
  question: string;
  state: "running" | "done" | "failed" | "interrupted";
  asked_by: string;
  started_at: string;
  finished_at: string | null;
  route: string | null;
  model: string | null;
  stop: string | null;
  answer: string | null;
  grounding: { unsupported: string[]; uncited: boolean } | null;
  usage: Usage | null;
  duration_s: number | null;
  error: string | null;
  steps?: Step[];
};

const EXAMPLES = [
  { text: "List experiments", note: "answered without a model" },
  { text: "Which experiments have a release verdict, and what do the verdicts say?", note: "uses the model" },
  { text: "What happened in the most recent workflow run, and was it verified?", note: "uses the model" },
];

export function AgentView() {
  return (
    <RequireIdentity>
      <Agent />
    </RequireIdentity>
  );
}

export type AgentFocus = "general" | "robotics" | "laboratory" | "release";

export function Agent({ initialQuestion, workspace, focus = "general" }: { initialQuestion?: string; workspace?: string; focus?: AgentFocus } = {}) {
  const { me, orgs, org: selectedOrg, select } = useOrg();
  const org = workspace ?? selectedOrg;
  const qc = useQueryClient();
  const [picked, setPicked] = useState<string | null>(null);
  const params = useSearchParams();
  const [question, setQuestion] = useState(initialQuestion ?? params.get("q") ?? ""); // the guided journey hands over its question
  const [propose, setPropose] = useState(!initialQuestion && !!params.get("q"));

  const proposals = useQuery({
    queryKey: ["agent-proposals", org],
    queryFn: () => api<Proposal[]>(`${orgPath(org!)}/experiment-proposals`),
    enabled: !!org,
  });
  const status = useQuery({
    queryKey: ["agent-status", org],
    queryFn: () => api<Status>(`${orgPath(org!)}/agent/status`),
    enabled: !!org,
  });
  const sessions = useQuery({
    queryKey: ["agent-sessions", org],
    queryFn: () => api<Session[]>(`${orgPath(org!)}/agent/sessions`),
    enabled: !!org,
    refetchInterval: (q) => (q.state.data?.some((s) => s.state === "running") ? 1500 : false),
  });
  const shownId = picked ?? (initialQuestion ? null : sessions.data?.[0]?.id) ?? null;
  const detail = useQuery({
    queryKey: ["agent-session", org, shownId],
    queryFn: () => api<Session>(`${orgPath(org!)}/agent/sessions/${shownId}`),
    enabled: !!org && !!shownId,
    refetchInterval: (q) => (q.state.data?.state === "running" ? 1200 : false),
  });
  const finished = detail.data && detail.data.state !== "running";
  useEffect(() => {
    if (finished) {
      void qc.invalidateQueries({ queryKey: ["agent-status", org] });
      void qc.invalidateQueries({ queryKey: ["agent-sessions", org] });
    }
  }, [finished, qc, org]);

  const ask = useMutation({
    mutationFn: (q: string) => api<Session>(`${orgPath(org!)}/agent/sessions`, { method: "POST", body: JSON.stringify({ question: q, propose, focus }) }),
    onSuccess: (s) => {
      setPicked(s.id);
      setQuestion("");
      void qc.invalidateQueries({ queryKey: ["agent-sessions", org] });
    },
  });

  if (me.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  if (!org) return <Notice tone="info">You have no workspace yet. Start on the <Link className="underline" href="/onboarding">Get started</Link> page.</Notice>;
  const st = status.data;
  const running = sessions.data?.some((s) => s.state === "running") ?? false;
  const canSubmit = !!st && st.can_ask && st.runner_available && !ask.isPending && !running && question.trim().length >= 3;

  return (
    <>
      {!initialQuestion && <PageHeader
        title="Agent"
        subtitle="Ask about this workspace's runs, experiments and recordings. The agent reads with your permissions, cites what it used and cannot approve, start or change anything."
        actions={<OrgSelect orgs={orgs} org={org} select={select} />}
      />}
      <div className={initialQuestion ? "space-y-4" : "grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]"}>
        <div className="min-w-0 space-y-4">
          <Panel title="Ask">
            {status.isLoading && <p className="text-[13px] text-muted">Loading…</p>}
            {status.error && <Notice tone="bad">Could not read the agent&apos;s status: {status.error.message}</Notice>}
            {st && !st.runner_available && (
              <Notice tone="warn">The agent is not available on this server (its runner is not installed, or it cannot keep sessions), so nothing can be asked here. The operator sets it up with a writable <span className="num">PAP_AGENT_STATE_PATH</span> and <span className="num">PAP_AGENT_COMMAND</span>.</Notice>
            )}
            {st && st.runner_available && !st.model_configured && (
              <div className="mb-3">
                <Notice tone="info">
                  No language model is set on this server. The fixed questions still work, with no model and no cost: <em>list experiments</em>, <em>status of run &lt;id&gt;</em>, <em>verdicts for &lt;experiment&gt;</em>. The operator sets{" "}
                  <span className="num">PAP_LLM_API_KEY</span>, <span className="num">PAP_LLM_BASE_URL</span> and <span className="num">PAP_LLM_MODEL</span> in the server&apos;s environment for anything else.
                </Notice>
              </div>
            )}
            {st && !st.can_ask && <p className="mb-2 text-[12px] text-muted">Asking costs model spend, so it needs the engineer role. You can read everything engineers ask.</p>}
            <form
              className="space-y-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (canSubmit) ask.mutate(question.trim());
              }}
            >
              <label htmlFor="agent-question" className="block text-[12px] text-muted">
                Question
              </label>
              <textarea
                id="agent-question"
                className="field block w-full"
                rows={3}
                maxLength={1000}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && canSubmit) ask.mutate(question.trim());
                }}
                disabled={!st?.can_ask}
              />
              {st?.can_ask && focus !== "release" && (
                <label className="flex items-start gap-2 text-[12px] text-muted">
                  <input type="checkbox" className="mt-0.5" checked={propose} onChange={(e) => setPropose(e.target.checked)} />
                  <span>Let the agent draft a follow-up experiment. A draft is not sent: you decide whether to file it, and someone other than you must approve it before anything runs.</span>
                </label>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn btn-primary" disabled={!canSubmit}>
                  {ask.isPending ? "Sending…" : "Ask"}
                </button>
                <span className="text-[12px] text-faint">Ctrl Enter also sends.</span>
                {running && <span role="status" className="text-[12px] text-muted">A session is running; one at a time.</span>}
              </div>
              {ask.error && <p className="text-[12px] text-bad">{ask.error.message}</p>}
            </form>
            {st?.can_ask && (
              <div className="mt-3">
                <h3 className="mb-1 text-[12px] font-medium text-faint">Examples</h3>
                <ul className="flex flex-wrap gap-1.5">
                  {EXAMPLES.map((ex) => (
                    <li key={ex.text}>
                      <button type="button" className="btn text-[12px]" onClick={() => setQuestion(ex.text)}>
                        {ex.text}
                        <span className="text-faint"> · {ex.note}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Panel>

          {shownId && (
            <Panel title="Session">
              {detail.isLoading && <p className="text-[13px] text-muted">Loading…</p>}
              {detail.error && <Notice tone="bad">Could not load this session: {detail.error.message}</Notice>}
              {detail.data && <SessionView s={detail.data} org={org} canFile={!!st?.can_ask} proposals={proposals.data ?? []} onFiled={() => void proposals.refetch()} />}
            </Panel>
          )}
        </div>

        <div className="min-w-0 space-y-4">
          {st && <Limits st={st} />}
          {!initialQuestion && <Panel title="Sessions">
            {sessions.isLoading && <p className="text-[13px] text-muted">Loading…</p>}
            {sessions.error && <Notice tone="bad">Could not list sessions: {sessions.error.message}</Notice>}
            {sessions.data && sessions.data.length === 0 && <p className="text-[13px] text-muted">No session yet. Ask a question to start one.</p>}
            <ul className="space-y-px">
              {sessions.data?.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => setPicked(s.id)}
                    aria-current={s.id === shownId ? "true" : undefined}
                    className={clsx(
                      "flex w-full items-start gap-2 rounded-[5px] px-2 py-1.5 text-left text-[12px] transition-colors duration-[80ms]",
                      s.id === shownId ? "bg-selected text-ink" : "text-muted hover:bg-hover hover:text-ink",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{s.question}</span>
                      <span className="num block whitespace-nowrap text-[11px] text-muted">
                        {s.asked_by} · <Time iso={s.started_at} />
                      </span>
                    </span>
                    <span className="shrink-0">
                      <StateBadge s={s} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>}
        </div>
      </div>
    </>
  );
}

function Limits({ st }: { st: Status }) {
  return (
    <Panel title="Limits">
      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[12px]">
        <dt className="text-muted">Model</dt>
        <dd>{st.model_configured ? <span className="num">{st.model}</span> : "none set"}</dd>
        <dt className="text-muted">Today</dt>
        <dd>
          {st.sessions_today} of {st.daily_sessions_cap} sessions
          {st.priced && <> · ${st.usd_today.toFixed(4)} of ${st.daily_usd_cap.toFixed(2)}</>}
        </dd>
        <dt className="text-muted">Each session</dt>
        <dd>
          {st.priced ? <>up to ${st.session_usd_cap.toFixed(2)}, </> : null}
          {st.max_steps} model calls, {Math.round(st.timeout_s)} s
        </dd>
      </dl>
      {!st.priced && st.model_configured && (
        <p className="mt-2 text-[12px] text-muted">No prices are set on the server, so sessions are bounded by tokens, not dollars, and no cost is shown.</p>
      )}
      <p className="mt-2 text-[12px] text-muted">Read-only: the agent cannot request, approve or run anything from this page.</p>
    </Panel>
  );
}

function StateBadge({ s }: { s: Session }) {
  if (s.state === "running") return <Badge tone="accent">running</Badge>;
  if (s.state === "failed" || s.state === "interrupted") return <Badge tone="bad">{s.state}</Badge>;
  return s.stop === "answered" ? <Badge tone="ok">answered</Badge> : <Badge tone="warn">stopped</Badge>;
}

/** A model can take a minute. Say so, show the time, and say the session does not need this page open. */
function Working({ startedAt }: { startedAt: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const i = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(i);
  }, []);
  const secs = Math.max(0, Math.round((now - Date.parse(startedAt)) / 1000));
  return (
    <p role="status" className="text-[13px] text-muted">
      The agent is working; a language model usually needs 20 to 90 seconds here. This view updates by itself, and you can leave this page: the session keeps running.{" "}
      <span aria-hidden className="num text-ink">{secs} s</span>
    </p>
  );
}

type DraftStep = { tool: "propose_experiment" | "request_experiment_run"; input: Record<string, unknown> };

/** A follow-up the agent drafted. It is not sent: filing is the person's decision, made here, as themselves. */
function DraftCard({ d, s, org, canFile, proposals, onFiled }: { d: DraftStep; s: Session; org: string; canFile: boolean; proposals: Proposal[]; onFiled: () => void }) {
  const input = d.input;
  const rationale = String(input.rationale ?? "");
  const tag = `agent-session:${s.id}`;
  const filedBefore = d.tool === "propose_experiment" && proposals.find((p) => (p.evidence_ids as unknown[]).includes(tag) && p.workflow === input.workflow);
  const file = useMutation({
    mutationFn: () =>
      d.tool === "propose_experiment"
        ? api<Proposal>(`${orgPath(org)}/experiment-proposals`, {
            method: "POST",
            headers: { "X-PAP-Channel": "agent-tools" },
            body: JSON.stringify({ workflow: input.workflow, rationale, evidence_ids: [...((input.evidence_ids as string[] | undefined) ?? []).slice(0, 18), tag] }),
          })
        : api<{ id: string }>(`${orgPath(org)}/experiments/${input.experiment}/versions/${input.version}/requests`, { method: "POST", body: JSON.stringify({ note: rationale }) }),
    onSuccess: onFiled,
  });
  const filed = filedBefore || file.data;
  return (
    <li className="rounded-sm border border-line p-3 text-[13px]">
      <p className="flex flex-wrap items-center gap-2">
        <Badge tone="accent">drafted, not filed</Badge>
        <span className="font-medium">
          {d.tool === "propose_experiment" ? <>Run the workflow <span className="num">{String(input.workflow)}</span></> : <>Run <span className="num">{String(input.experiment)}</span> version {String(input.version)}</>}
        </span>
      </p>
      <p className="mt-1 text-muted">{rationale}</p>
      {Array.isArray(input.evidence_ids) && input.evidence_ids.length > 0 && <p className="num mt-1 break-all text-[11px] text-muted">{(input.evidence_ids as string[]).join(", ")}</p>}
      {filed ? (
        <p role="status" className="mt-2 text-[12px]">
          <Badge tone="ok">filed</Badge> It is waiting for someone other than whoever filed it. Decide it in{" "}
          <Link className="underline" href={`/workflows?org=${org}`}>Workflows</Link>.
        </p>
      ) : canFile ? (
        <div className="mt-2 flex items-center gap-2">
          <button type="button" className="btn" disabled={file.isPending} onClick={() => file.mutate()}>
            {file.isPending ? "Filing…" : "File as a proposal"}
          </button>
          <span className="text-[12px] text-muted">Records it as you. Nothing runs until someone else approves it.</span>
          {file.error && <span role="alert" className="text-[12px] text-bad">{file.error.message}</span>}
        </div>
      ) : (
        <p className="mt-2 text-[12px] text-muted">An engineer can file this.</p>
      )}
    </li>
  );
}

function SessionView({ s, org, canFile, proposals, onFiled }: { s: Session; org: string; canFile: boolean; proposals: Proposal[]; onFiled: () => void }) {
  const fast = s.route?.startsWith("fast:") ?? false;
  const g = s.grounding;
  const drafts: DraftStep[] = (s.steps ?? [])
    .filter((st) => st.kind === "tool" && (st.tool === "propose_experiment" || st.tool === "request_experiment_run") && (st.output as { drafted?: boolean } | null)?.drafted)
    .map((st) => ({ tool: st.tool as DraftStep["tool"], input: (st.input ?? {}) as Record<string, unknown> }));
  return (
    <div className="space-y-3" aria-live="polite">
      <div>
        <p className="text-[13px] font-medium">{s.question}</p>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-muted">
          <StateBadge s={s} />
          {s.state !== "running" && (fast ? <Badge tone="neutral">no model used</Badge> : s.model && s.model !== "none" ? <Badge tone="neutral">{s.model}</Badge> : null)}
          <span>
            asked by {s.asked_by} · <Time iso={s.started_at} />
          </span>
        </p>
      </div>

      {s.state === "running" && <Working startedAt={s.started_at} />}
      {(s.state === "failed" || s.state === "interrupted") && (
        <Notice tone="bad">
          {s.state === "interrupted" ? "This session was interrupted." : "This session failed."} {s.error} Ask again, or ask a fixed question such as “list experiments”.
        </Notice>
      )}

      {s.state === "done" && (
        <>
          {s.answer ? (
            <section aria-labelledby="answer-h">
              <h3 id="answer-h" className="mb-1 text-[12px] font-medium text-faint">
                Answer
              </h3>
              <div className="rounded-sm border border-line bg-bg p-3 text-[13px] leading-relaxed">
                <Markdown text={s.answer} />
              </div>
              <p className="mt-1 text-[11px] text-muted">
                {fast
                  ? "Answered by a fixed tool call and a template: no model."
                  : "Written by a language model from the tool results in the trace. Check the cited ids there before relying on it."}
              </p>
            </section>
          ) : (
            <Notice tone="warn">
              {s.stop?.startsWith("failed:") && s.usage?.model_calls === 0 ? (
                <>
                  The model provider could not answer, so nothing was spent. This is usually brief: ask again, or run <em>Rule-based investigation (no model)</em> from the Lab experiment page, which needs no model.{" "}
                  <span className="num text-[11px]">{s.stop.slice(0, 160)}</span>
                </>
              ) : (
                <>No answer. {s.stop}</>
              )}
            </Notice>
          )}
          {s.answer && s.stop !== "answered" && <Notice tone="warn">{s.stop}</Notice>}
          {g && (g.unsupported.length > 0 || g.uncited) && (
            <Notice tone="warn">
              Check this answer before relying on it.{" "}
              {g.unsupported.length > 0 && <>It cites ids no tool returned: <span className="num">{g.unsupported.join(", ")}</span>. </>}
              {g.uncited && <>It used tool results without citing an id.</>}
            </Notice>
          )}
          {drafts.length > 0 && (
            <section aria-labelledby="drafts-h">
              <h3 id="drafts-h" className="mb-1 text-[12px] font-medium text-faint">
                Follow-up the agent drafted
              </h3>
              <ul className="space-y-2">
                {drafts.map((d, i) => (
                  <DraftCard key={i} d={d} s={s} org={org} canFile={canFile} proposals={proposals} onFiled={onFiled} />
                ))}
              </ul>
            </section>
          )}
          {s.usage && (
            <p className="num text-[12px] text-muted">
              {s.usage.model_calls} model calls · {s.usage.input_tokens} in / {s.usage.output_tokens} out tokens ·{" "}
              {s.usage.usd === null ? "cost unknown (no prices set)" : `$${s.usage.usd.toFixed(4)}`}
              {s.duration_s !== null && <> · {s.duration_s.toFixed(1)} s</>}
            </p>
          )}
        </>
      )}

      {s.steps && s.steps.length > 0 && (
        <details className="text-[12px]">
          <summary className="cursor-pointer text-muted">Trace ({s.steps.length} steps)</summary>
          <p className="mt-1 text-[11px] text-muted">
            Every tool call and model call, in order. Each tool result keeps its digest, so a finding can be traced to the exact record it read.
          </p>
          <ol className="mt-2 space-y-2">
            {s.steps.map((st) => (
              <li key={st.n} className="rounded-sm border border-line p-2">
                {st.kind === "model" ? (
                  <p className="num text-muted">
                    {st.n}. model call · {st.input_tokens} in / {st.output_tokens} out tokens
                  </p>
                ) : (
                  <>
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="num">
                        {st.n}. {st.tool}
                      </span>
                      {st.permitted === false && <Badge tone="bad">refused</Badge>}
                      {st.output_sha256 && <span className="num text-muted">{shortDigest(st.output_sha256)}</span>}
                    </p>
                    {st.error && <p className="text-bad">{st.error}</p>}
                    <pre className="num mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all text-[11px] text-muted">
                      {`input ${JSON.stringify(st.input)}`}
                      {st.output !== undefined && st.output !== null ? `\noutput ${JSON.stringify(st.output, null, 1).slice(0, 4000)}` : ""}
                    </pre>
                  </>
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
