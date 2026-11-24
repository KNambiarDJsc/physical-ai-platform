import clsx from "clsx";
import type { ReactNode } from "react";
import { CLASS_LABEL, timestamp, VERDICT_LABEL } from "@/lib/format";

/** A stored instant, shown in the one timestamp format; the exact ISO value is in the tooltip. */
export function Time({ iso }: { iso: string | null | undefined }) {
  if (!iso) return <span className="text-faint">—</span>;
  return (
    <time dateTime={iso} title={iso} className="num text-muted">
      {timestamp(iso)}
    </time>
  );
}

export function Badge({ tone, children }: { tone: "ok" | "bad" | "warn" | "unknown" | "neutral" | "accent"; children: ReactNode }) {
  const cls = {
    ok: "bg-ok-soft text-ok",
    bad: "bg-bad-soft text-bad",
    warn: "bg-warn-soft text-warn",
    unknown: "bg-unknown-soft text-unknown",
    neutral: "bg-sunken text-muted",
    accent: "bg-accent-soft text-accent",
  }[tone];
  return <span className={clsx("state-fade inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium", cls)}>{children}</span>;
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const tone = verdict === "regression" ? "bad" : verdict === "improvement" ? "ok" : verdict === "no_change" ? "neutral" : "warn";
  return <Badge tone={tone}>{VERDICT_LABEL[verdict] ?? verdict}</Badge>;
}

export function StateBadge({ state }: { state: string }) {
  const tone = state === "succeeded" ? "ok" : state === "failed" ? "bad" : state === "cancelled" ? "neutral" : "accent";
  return <Badge tone={tone}>{state}</Badge>;
}

export function ClassBadge({ value }: { value: string }) {
  const tone =
    value === "supported_success" || value === "verified_success"
      ? "ok"
      : value === "verified_failure"
        ? "bad"
        : value === "contradiction"
          ? "warn"
          : "unknown";
  return <Badge tone={tone}>{CLASS_LABEL[value] ?? value}</Badge>;
}

export function EvidenceClassBadge({ classes }: { classes: readonly string[] | undefined }) {
  if (!classes || classes.length === 0) return null;
  const synthetic = classes.includes("synthetic") || classes.includes("simulated");
  return <Badge tone={synthetic ? "warn" : "neutral"}>{classes.join(", ").toUpperCase()} EVIDENCE</Badge>;
}

export function Table({ head, children, caption }: { head: ReactNode[]; children: ReactNode; caption?: string }) {
  return (
    <div className="scroll-x overflow-x-auto" role="region" aria-label={caption ?? "Scrollable table"} tabIndex={0}>
      <table className="w-full border-collapse text-[13px]">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            {head.map((h, i) => (
              <th key={i} scope="col" className="px-2 py-1.5 align-bottom font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}

export function Td({ children, num, className }: { children: ReactNode; num?: boolean; className?: string }) {
  const wraps = className?.includes("whitespace-");
  return <td className={clsx("px-2 py-1.5 align-top", !wraps && "whitespace-nowrap", num && "num text-right", className)}>{children}</td>;
}

/**
 * Draws intervals the engine computed on a 0–100 % axis. It computes nothing: the point and bounds are inputs.
 */
export function IntervalPlot({
  rows,
}: {
  rows: { label: string; rate: number | null | undefined; ci: readonly [number, number] | null | undefined }[];
}) {
  const w = 320;
  const pad = 70;
  const x = (v: number) => pad + v * (w - pad - 10);
  return (
    <svg viewBox={`0 0 ${w} ${rows.length * 22 + 18}`} role="img" aria-label="Failure rate with 95% interval per release" className="w-full min-w-[260px] max-w-md">
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={0} y2={rows.length * 22} stroke="var(--color-line)" />
          <text x={x(t)} y={rows.length * 22 + 13} fontSize="9" textAnchor="middle" fill="var(--color-faint)">
            {t * 100}%
          </text>
        </g>
      ))}
      {rows.map((r, i) => {
        const y = i * 22 + 11;
        return (
          <g key={r.label}>
            <text x={0} y={y + 3} fontSize="10" fill="var(--color-muted)">
              {r.label}
            </text>
            {r.ci && <line x1={x(r.ci[0])} x2={x(r.ci[1])} y1={y} y2={y} stroke="var(--color-accent)" strokeWidth={3} strokeLinecap="round" />}
            {r.rate !== null && r.rate !== undefined && <circle cx={x(r.rate)} cy={y} r={3.5} fill="var(--color-ink)" />}
          </g>
        );
      })}
    </svg>
  );
}
