import Link from "next/link";
import type { EpisodeDetail } from "@/lib/api/client";
import { CLASS_LABEL, shortDigest } from "@/lib/format";
import { Panel } from "./AppShell";
import { Badge, ClassBadge, Table, Td } from "./ui";

type Cond = { name?: string; evidence: string; op: string; result: string; observed: unknown[]; records: string[] };
type Reason = { code: string; detail?: string; item?: string; record?: string };
type Report = {
  verdict: string;
  verifier: string;
  conditions: Cond[];
  reasons: Reason[];
  items: Record<string, { accepted: string[]; rejected: Reason[]; anchor: boolean }>;
  contract: { name: string; version: string; sha256: string };
};
type Avail = { available: boolean; value: string | null };

function value(v: unknown): string {
  if (v && typeof v === "object" && "value" in v) {
    const q = v as { value: unknown; unit?: string };
    return `${String(q.value)}${q.unit ? ` ${q.unit}` : ""}`;
  }
  return JSON.stringify(v);
}

const WHY: Record<string, string> = {
  supported_success: "The robot reported success and every condition held on the independent evidence.",
  verified_success: "No usable report, but every condition held on the independent evidence.",
  verified_failure: "Valid independent evidence shows a condition did not hold, and the robot did not claim success.",
  contradiction: "The robot's report and the independent evidence disagree.",
  unknown: "Evidence was present, but the verifier could not decide; the reasons say why.",
  reported_only: "Only the robot's own report exists for this episode; nothing independent was measured.",
  insufficient_evidence: "Neither a usable report nor independent evidence exists for this episode.",
};

/** Everything the verifier and the mapping recorded about one episode. Nothing here is computed. */
export function EpisodeDetailView({ ep, twin }: { ep: EpisodeDetail; twin?: string }) {
  const report = ep.verifier_report as Report | null;
  const doc = ep.document as Record<string, unknown>;
  const field = (k: string) => {
    const f = doc[k] as Avail | undefined;
    return f?.available ? f.value : <Badge tone="neutral">unavailable</Badge>;
  };
  return (
    <Panel title={`Episode ${ep.episode_key}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <ClassBadge value={ep.outcome_class} />
        <span className="text-[13px] text-muted">{WHY[ep.outcome_class] ?? CLASS_LABEL[ep.outcome_class]}</span>
        {twin && (
          <Link className="btn ml-auto" href={twin}>
            Open in Workbench
          </Link>
        )}
      </div>
      <dl className="mb-4 grid gap-x-6 gap-y-1 text-[13px] break-all sm:grid-cols-[max-content_1fr]">
        <dt className="text-muted">Robot reported</dt>
        <dd className="num">
          {ep.reported}
          {doc.reported_raw ? ` (source value "${String(doc.reported_raw)}")` : ""}
        </dd>
        <dt className="text-muted">Verifier verdict</dt>
        <dd className="num">{ep.verdict ?? "not run (no contract)"}</dd>
        <dt className="text-muted">Robot / site / scenario</dt>
        <dd className="num">
          {ep.robot} / {field("site")} / {field("scenario")}
        </dd>
        <dt className="text-muted">Started / ended</dt>
        <dd className="num">
          {field("started_at")} / {ep.ended_at} <span className="text-faint">({String(doc.clock_domain)})</span>
        </dd>
        <dt className="text-muted">Source</dt>
        <dd className="num">
          artifact {shortDigest((doc.source as { artifact_sha256: string }).artifact_sha256)}, row {ep.source_row}
        </dd>
        <dt className="text-muted">Mapping</dt>
        <dd className="num">{String(doc.mapping)}</dd>
        <dt className="text-muted">Evidence class</dt>
        <dd className="num">{String(doc.evidence_class)}</dd>
      </dl>
      {report && (
        <>
          <h3 className="mb-1 text-[13px] font-semibold">
            Conditions <span className="font-normal text-muted">({report.contract.name} v{report.contract.version}, {report.verifier})</span>
          </h3>
          <Table head={["Condition", "Evidence", "Result", "Observed"]} caption="Conditions judged by the verifier">
            {report.conditions.map((c, i) => (
              <tr key={i}>
                <Td>{c.name ?? `${c.evidence} ${c.op}`}</Td>
                <Td className="num">{c.evidence}</Td>
                <Td>
                  <Badge tone={c.result === "TRUE" ? "ok" : c.result === "FALSE" ? "bad" : "unknown"}>{c.result.toLowerCase()}</Badge>
                </Td>
                <Td className="num">{c.observed.length ? c.observed.map(value).join(", ") : "no record"}</Td>
              </tr>
            ))}
          </Table>
          {report.reasons.length > 0 && (
            <>
              <h3 className="mb-1 mt-4 text-[13px] font-semibold">Verifier reasons</h3>
              <ul className="space-y-1 text-[13px]">
                {report.reasons.map((r, i) => (
                  <li key={i}>
                    <span className="num text-warn">{r.code}</span>
                    {r.item && <span className="text-muted"> · {r.item}</span>} — {r.detail}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </Panel>
  );
}
