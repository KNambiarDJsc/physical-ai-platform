"use client";

import clsx from "clsx";
import type { ReactNode } from "react";
import { Badge } from "./ui";

/**
 * Renders any JSON a device property returns (DESIGN.md §6: an interaction model per module, not a card grid).
 * Arrays of records become tables, records become definition lists, and the words observers use for freshness
 * (fresh, stale, never, missing, latched ...) become badges. Nothing is computed or filled in: an absent value is "—".
 */

type Tone = "ok" | "bad" | "warn" | "unknown" | "neutral" | "accent";

const STATE_TONE: Record<string, Tone> = {
  fresh: "ok", running: "ok", active: "ok", received: "ok", OK: "ok",
  stale: "warn", never: "warn", WARN: "warn", STALE: "warn", inactive: "warn", silent: "warn",
  ERROR: "bad", error: "bad",
  latched: "neutral", pending: "neutral", no_publishers: "neutral", absent: "neutral", no_messages: "neutral",
  missing: "unknown", not_sampled: "unknown", unconfigured: "unknown",
};

export function ObsState({ value, strong }: { value: string; strong?: boolean }) {
  // A required item that is missing or silent is a problem; the same word on an optional one is not.
  const tone = strong ? "bad" : (STATE_TONE[value] ?? "neutral");
  return <Badge tone={tone}>{value.replace(/_/g, " ")}</Badge>;
}

const STATE_KEYS = new Set(["state", "level", "clock_state"]);
const PROBLEM = new Set(["missing", "stale", "never", "no_publishers"]);

export function num(n: number, key = ""): string {
  if (key.endsWith("_s") || key === "age_s") return `${Number.isInteger(n) ? n : n.toFixed(Math.abs(n) < 10 ? 3 : 1)} s`;
  if (key.endsWith("_hz")) return `${n.toFixed(1)} Hz`;
  if (Number.isInteger(n)) return String(n);
  return Math.abs(n) >= 1000 ? n.toFixed(1) : String(Number(n.toPrecision(5)));
}

function cell(key: string, v: unknown, row: Record<string, unknown>): ReactNode {
  if (v === null || v === undefined) return <span className="text-faint">—</span>;
  if (STATE_KEYS.has(key) && typeof v === "string") {
    return <ObsState value={v} strong={row.required === true && PROBLEM.has(v)} />;
  }
  if (typeof v === "number") return <span className="num">{num(v, key)}</span>;
  if (typeof v === "boolean") return <span className="text-muted">{v ? "yes" : "no"}</span>;
  if (typeof v === "string") return v;
  if (Array.isArray(v)) {
    const flat = v.every((x) => typeof x !== "object" || x === null);
    return <span className="num text-muted">{flat && v.length <= 4 ? v.map((x) => (typeof x === "number" ? num(x) : String(x))).join(", ") : `${v.length} items`}</span>;
  }
  return <span className="num text-muted">{`{${Object.keys(v as object).length}}`}</span>;
}

function isRecordArray(v: unknown): v is Record<string, unknown>[] {
  return Array.isArray(v) && v.length > 0 && v.every((x) => x && typeof x === "object" && !Array.isArray(x));
}

export function RecordTable({ rows, caption }: { rows: Record<string, unknown>[]; caption: string }) {
  const keys: string[] = [];
  for (const r of rows.slice(0, 50)) for (const k of Object.keys(r)) if (!keys.includes(k)) keys.push(k);
  const scalar = keys.filter((k) => rows.some((r) => r[k] !== null && typeof r[k] !== "object") || rows.every((r) => r[k] === null || r[k] === undefined));
  // JSON keys arrive sorted alphabetically: lead with what identifies the row, then its state, then the rest.
  const rank = (k: string) => {
    const i = ["name", "topic", "child", "service", "key", "state", "level", "required"].indexOf(k);
    return i === -1 ? 99 : i;
  };
  const shown = scalar
    .filter((k) => !["types", "header_stamp_s", "stale_after_s", "not_sampled_reason", "latched"].includes(k))
    .sort((a, b) => rank(a) - rank(b))
    .slice(0, 8);
  const extra = keys.filter((k) => !shown.includes(k));
  return (
    // Wide tables scroll sideways: the container must be reachable by keyboard (WCAG 2.1.1), so it is a labelled region.
    <div role="region" aria-label={`${caption}, scrollable table`} tabIndex={0} className="overflow-x-auto rounded-md border border-line">
      <table className="w-full border-collapse text-[12.5px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line text-left text-[12px] text-muted">
            {shown.map((k) => (
              <th key={k} scope="col" className="whitespace-nowrap px-2 py-1.5 font-medium">
                {k.replace(/_/g, " ")}
              </th>
            ))}
            {extra.length > 0 && <th scope="col" className="px-2 py-1.5 font-medium">more</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r, i) => (
            <tr key={i} className="align-top">
              {shown.map((k) => (
                <td key={k} className={clsx("whitespace-nowrap px-2 py-1", typeof r[k] === "number" && "text-right")}>
                  {cell(k, r[k], r)}
                </td>
              ))}
              {extra.length > 0 && <td className="px-2 py-1">{extra.map((k) => <NestedHint key={k} k={k} v={r[k]} />)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NestedHint({ k, v }: { k: string; v: unknown }) {
  if (v === null || v === undefined) return null;
  if (Array.isArray(v)) return <span className="num mr-2 text-[11.5px] text-faint">{k}: {v.length}</span>;
  if (typeof v === "object") return <span className="num mr-2 text-[11.5px] text-faint">{k}: …</span>;
  return null;
}

export function ValueView({ value, name, depth = 0 }: { value: unknown; name: string; depth?: number }) {
  if (value === null || value === undefined) return <span className="text-faint">—</span>;
  if (isRecordArray(value)) {
    // Nested arrays and records (a source's joints, a manager's controllers) are shown under the table, labelled by the
    // row that owns them; short flat arrays (a position, a quaternion) stay inline in their cell.
    const nested = value.flatMap((r, i) =>
      Object.entries(r)
        .filter(([, v]) => v !== null && typeof v === "object" && !(Array.isArray(v) && v.length <= 4 && v.every((x) => typeof x !== "object")))
        .filter(([k]) => k !== "types")
        .map(([k, v]) => ({ label: String(r.topic ?? r.name ?? r.service ?? r.child ?? i + 1), k, v })),
    );
    return (
      <div className="space-y-3">
        <RecordTable rows={value} caption={name} />
        {nested.map((n, i) => (
          <section key={`${n.label}-${n.k}-${i}`} aria-label={`${n.k.replace(/_/g, " ")} of ${n.label}`}>
            <h4 className="mb-1 text-[12px] font-medium text-faint">
              <span className="num">{n.label}</span> · {n.k.replace(/_/g, " ")}
              {Array.isArray(n.v) && <span className="num"> · {n.v.length}</span>}
            </h4>
            <ValueView value={n.v} name={n.k} depth={depth + 1} />
          </section>
        ))}
      </div>
    );
  }
  if (Array.isArray(value)) return <span className="num text-[12.5px]">{value.length === 0 ? "none" : value.map(String).join(", ")}</span>;
  if (typeof value !== "object") return <span className="num text-[12.5px]">{typeof value === "number" ? num(value, name) : String(value)}</span>;
  const rec = value as Record<string, unknown>;
  const simple = Object.entries(rec).filter(([, v]) => v === null || typeof v !== "object");
  const complex = Object.entries(rec).filter(([, v]) => v !== null && typeof v === "object");
  return (
    <div className="space-y-3">
      {simple.length > 0 && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-[12.5px]">
          {simple.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k.replace(/_/g, " ")}</dt>
              <dd>{cell(k, v, rec)}</dd>
            </div>
          ))}
        </dl>
      )}
      {complex.map(([k, v]) => (
        <section key={k} aria-label={k.replace(/_/g, " ")}>
          <h4 className={clsx("mb-1 text-[12px] font-medium text-faint", depth > 1 && "sr-only")}>
            {k.replace(/_/g, " ")}
            {Array.isArray(v) && <span className="num"> · {v.length}</span>}
          </h4>
          <ValueView value={v} name={k} depth={depth + 1} />
        </section>
      ))}
    </div>
  );
}
