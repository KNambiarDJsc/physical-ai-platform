"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api, orgPath, type Proposal, type Workflow, type WorkflowTemplate } from "@/lib/api/client";
import { shortDigest } from "@/lib/format";
import { Notice, PageHeader, Panel } from "./AppShell";
import { RequireIdentity } from "./Identity";
import { KindBadge } from "./Hardware";
import { Badge, ClassBadge, Table, Td, Time } from "./ui";
import { VerdictBadge } from "./Workbench";
import { OrgSelect, RUN_STATE, useEnvironments, useOrg, useRuns, useWorkflows } from "./Workspace";

export function WorkflowsView() {
  return (
    <RequireIdentity>
      <Workflows />
    </RequireIdentity>
  );
}

function Workflows() {
  const { me, orgs, org, role, select } = useOrg();
  const workflows = useWorkflows(org);
  const runs = useRuns(org);
  if (me.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  return (
    <>
      <PageHeader
        title="Workflows"
        subtitle="Ordered device actions with a verification contract. Runs execute in the worker; the engine judges the result."
        actions={<OrgSelect orgs={orgs} org={org} select={select} />}
      />
      {!org ? (
        <Notice tone="info">You have no workspace yet. Start on the <Link className="underline" href="/onboarding">Get started</Link> page.</Notice>
      ) : (
        <div className="space-y-4">
          <Panel title="Workflows">
            {workflows.data && workflows.data.length === 0 && <p className="text-[13px] text-muted">No workflow yet.</p>}
            {workflows.data && workflows.data.length > 0 && (
              <Table head={["Workflow", "Environment", "Steps", "Verification", "Definition", ""]} caption="Workflows">
                {workflows.data.map((w) => (
                  <WorkflowRow key={w.id} org={org} w={w} />
                ))}
              </Table>
            )}
          </Panel>
          <Proposals org={org} canDecide={role === "engineer" || role === "admin"} />
          {role !== "viewer" && <NewWorkflow org={org} />}
          <Panel title="Recent runs">
            {runs.data && runs.data.length === 0 && <p className="text-[13px] text-muted">No run yet.</p>}
            {runs.data && runs.data.length > 0 && (
              <Table head={["Started", "Workflow", "State", "Reported", "Verified", "Outcome"]} caption="Recent workflow runs">
                {runs.data.map((r) => (
                  <tr key={r.id}>
                    <Td>
                      <Link className="text-accent hover:underline" href={`/workbench?org=${org}&run=${r.id}`}>
                        <Time iso={r.created_at} />
                      </Link>
                    </Td>
                    <Td>{r.workflow_name}</Td>
                    <Td>{RUN_STATE[r.state] ?? r.state}</Td>
                    <Td>{r.reported ? <Badge tone={(r.reported as { value?: string }).value === "succeeded" ? "ok" : "bad"}>{String((r.reported as { value?: string }).value)}</Badge> : "—"}</Td>
                    <Td>{r.verdict ? <VerdictBadge verdict={r.verdict} /> : "—"}</Td>
                    <Td>{r.outcome_class ? <ClassBadge value={r.outcome_class} /> : "—"}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Panel>
        </div>
      )}
    </>
  );
}

function WorkflowRow({ org, w }: { org: string; w: Workflow }) {
  const def = w.definition as { steps?: unknown[]; verification?: { contract?: string } };
  return (
    <tr>
      <Td>
        <span className="font-medium">{w.name}</span> <span className="num text-faint">{w.slug}</span>
      </Td>
      <Td className="num text-muted">{w.environment}</Td>
      <Td num>{def.steps?.length ?? 0}</Td>
      <Td className="num text-muted">{def.verification?.contract ?? "none"}</Td>
      <Td className="num text-muted" >sha256:{shortDigest(w.definition_sha256)}</Td>
      <Td>
        <Link className="btn py-0.5" href={`/workbench?org=${org}&workflow=${w.slug}`}>
          Open in Workbench
        </Link>
      </Td>
    </tr>
  );
}

export function useTemplates(org: string | null) {
  return useQuery({
    queryKey: ["templates", org],
    queryFn: () => api<WorkflowTemplate[]>(`${orgPath(org!)}/workflow-templates`),
    enabled: !!org,
  });
}

type ParamSchema = { properties?: Record<string, { type?: string; default?: unknown; description?: string; title?: string }> };

/** A form for one template, generated from the template's own JSON Schema (no field is hand-written here). */
export function TemplateForm({
  org,
  onCreated,
  defaultSlug = "dispense-check",
}: {
  org: string;
  onCreated?: (w: Workflow) => void;
  defaultSlug?: string;
}) {
  const qc = useQueryClient();
  const templates = useTemplates(org);
  const envs = useEnvironments(org);
  const simulated = (envs.data ?? []).filter((e) => e.kind === "simulated");
  const tpl = templates.data?.[0];
  const schema = (tpl?.parameters ?? {}) as ParamSchema;
  const [values, setValues] = useState<Record<string, string>>({});
  const [slug, setSlug] = useState(defaultSlug);
  const [env, setEnv] = useState("");
  const create = useMutation({
    mutationFn: () => {
      const parameters: Record<string, unknown> = {};
      for (const [k, p] of Object.entries(schema.properties ?? {})) {
        const raw = values[k] ?? (p.default === undefined ? "" : String(p.default));
        if (raw === "") continue;
        parameters[k] = p.type === "number" || p.type === "integer" ? Number(raw) : raw;
      }
      const body = { slug, name: tpl?.title ?? slug, environment: env || simulated[0]?.slug, template: tpl?.key, parameters };
      return api<Workflow>(`${orgPath(org)}/workflows`, { method: "POST", body: JSON.stringify(body) });
    },
    onSuccess: (w) => {
      void qc.invalidateQueries({ queryKey: ["workflows", org] });
      onCreated?.(w);
    },
  });
  if (!tpl) return <p className="text-[13px] text-muted">Loading templates…</p>;
  if (simulated.length === 0) return <Notice tone="info">Connect a simulated environment and discover its devices first (Hardware Hub).</Notice>;
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <p className="max-w-3xl text-[13px] text-muted">
        <span className="font-medium text-ink">{tpl.title}.</span> {tpl.description}
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-[13px]">
          <span className="mb-1 block text-muted">Name (slug)</span>
          <input className="field w-48" value={slug} onChange={(e) => setSlug(e.target.value)} pattern="[a-z0-9][a-z0-9\-]{0,62}" required />
        </label>
        <label className="text-[13px]">
          <span className="mb-1 block text-muted">Environment</span>
          <select className="field" value={env || simulated[0]?.slug} onChange={(e) => setEnv(e.target.value)}>
            {simulated.map((e) => (
              <option key={e.slug} value={e.slug}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        {Object.entries(schema.properties ?? {}).map(([k, p]) => (
          <label key={k} className="text-[13px]">
            <span className="mb-1 block text-muted">{p.description ?? p.title ?? k}</span>
            <input
              className="field w-40"
              name={k}
              inputMode={p.type === "number" ? "decimal" : undefined}
              value={values[k] ?? (p.default === undefined ? "" : String(p.default))}
              onChange={(e) => setValues({ ...values, [k]: e.target.value })}
            />
          </label>
        ))}
        <button className="btn btn-primary" type="submit" disabled={create.isPending}>
          Create workflow
        </button>
      </div>
      {create.error && <Notice tone="bad">{create.error.message}</Notice>}
    </form>
  );
}

function NewWorkflow({ org }: { org: string }) {
  const [made, setMade] = useState<Workflow | null>(null);
  return (
    <Panel title="New workflow from a template">
      <TemplateForm org={org} onCreated={setMade} />
      {made && (
        <p role="status" className="mt-3 text-[13px] text-muted">
          Created <span className="num text-ink">{made.slug}</span>.{" "}
          <Link className="text-accent underline" href={`/workbench?org=${org}&workflow=${made.slug}`}>
            Run it in the Workbench
          </Link>
          .
        </p>
      )}
    </Panel>
  );
}

const PROPOSAL_TONE = { proposed: "warn", approved: "ok", rejected: "neutral" } as const;

/** Experiments someone (often an assistant) proposed. Only an engineer decides; an approval queues an ordinary run. */
function Proposals({ org, canDecide }: { org: string; canDecide: boolean }) {
  const qc = useQueryClient();
  const proposals = useQuery({
    queryKey: ["proposals", org],
    queryFn: () => api<Proposal[]>(`${orgPath(org)}/experiment-proposals`),
    refetchInterval: 4000,
  });
  const decide = useMutation({
    mutationFn: ({ id, verb }: { id: string; verb: "approve" | "reject" }) =>
      api<Proposal>(`${orgPath(org)}/experiment-proposals/${id}/${verb}`, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["proposals", org] });
      void qc.invalidateQueries({ queryKey: ["runs", org] });
    },
  });
  const list = proposals.data ?? [];
  return (
    <Panel title="Proposed experiments">
      {proposals.error && <Notice tone="bad">{proposals.error.message}</Notice>}
      {list.length === 0 && !proposals.error && (
        <p className="text-[13px] text-muted">
          None. Anyone in the workspace, or an assistant using the read-only tools, can propose running an existing workflow; an engineer decides.
        </p>
      )}
      {decide.error && <Notice tone="bad">{decide.error.message}</Notice>}
      {list.length > 0 && (
        <Table head={["Proposed", "Workflow", "By", "Why", "Cited evidence", "State", ""]} caption="Proposed experiments">
          {list.map((p) => (
            <tr key={p.id}>
              <Td>
                <Time iso={p.created_at} />
              </Td>
              <Td className="whitespace-normal">
                <span className="num">{p.workflow}</span> <KindBadge kind={p.environment_kind} />
              </Td>
              <Td className="whitespace-normal">
                {p.proposed_by.replace(/^dev:/, "")} {p.channel === "agent-tools" && <Badge tone="accent">via assistant tools</Badge>}
              </Td>
              <Td className="max-w-md whitespace-normal">{p.rationale}</Td>
              <Td className="num max-w-xs whitespace-normal text-muted">{p.evidence_ids.length ? p.evidence_ids.join(", ") : "—"}</Td>
              <Td>
                <Badge tone={PROPOSAL_TONE[p.state as keyof typeof PROPOSAL_TONE] ?? "neutral"}>{p.state}</Badge>
              </Td>
              <Td className="whitespace-normal">
                {p.state === "proposed" && canDecide && (
                  <span className="flex gap-2">
                    <button className="btn btn-primary py-0.5" disabled={decide.isPending || p.environment_kind !== "simulated"} onClick={() => decide.mutate({ id: p.id, verb: "approve" })} aria-label={`Approve proposal for ${p.workflow}`} title={p.environment_kind !== "simulated" ? "Only simulated environments can be approved" : undefined}>
                      Approve
                    </button>
                    <button className="btn py-0.5" disabled={decide.isPending} onClick={() => decide.mutate({ id: p.id, verb: "reject" })} aria-label={`Reject proposal for ${p.workflow}`}>
                      Reject
                    </button>
                  </span>
                )}
                {p.state === "approved" && p.run_id && (
                  <Link className="text-accent hover:underline" href={`/workbench?org=${org}&run=${p.run_id}`}>
                    Open the run
                  </Link>
                )}
                {p.state === "proposed" && !canDecide && <span className="text-faint">awaiting an engineer</span>}
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </Panel>
  );
}
