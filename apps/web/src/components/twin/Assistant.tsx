"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, orgPath, type ToolCall } from "@/lib/api/client";
import type { TwinEvent } from "@/lib/twin";
import { Badge } from "../ui";

type Finding = { id: string; severity: "bad" | "warn" | "info"; statement: string; evidence: string[] };
type Explanation = {
  recording: { id: string; label: string; sha256: string; clock: string };
  event: { id: string; t: number; title: string; severity: string };
  findings: Finding[];
  not_known: string[];
  basis: string;
};

const TONE: Record<Finding["severity"], "bad" | "warn" | "neutral"> = { bad: "bad", warn: "warn", info: "neutral" };

/**
 * Asks the platform's own typed, read-only tools about the selected event (the same tools the MCP server serves, run as
 * the signed-in user). Nothing is generated: every sentence below comes from the tool, with the ids of the evidence it
 * rests on. A person's question is a button, not free text, because there is no language model behind it.
 */
export function Assistant({ org, project, recordingId, event }: { org: string; project: string; recordingId: string; event: TwinEvent | null }) {
  const [call, setCall] = useState<ToolCall | null>(null);
  const ask = useMutation({
    mutationFn: (ev: TwinEvent) =>
      api<ToolCall>(`${orgPath(org)}/assistant/tools/explain_recording_event`, {
        method: "POST",
        body: JSON.stringify({ arguments: { project, recording_id: recordingId, event_id: ev.id } }),
      }),
    onSuccess: setCall,
  });
  const ex = call && !call.is_error && call.tool === "explain_recording_event" ? (call.result as Explanation) : null;
  const stale = ex !== null && event !== null && ex.event.id !== event.id;
  return (
    <section aria-labelledby="assist-h" className="border-t border-line p-3" data-testid="assistant">
      <h2 id="assist-h" className="mb-1 text-[12px] font-medium text-faint">
        Engineering assistant
      </h2>
      <p className="mb-2 text-[12px] text-muted">
        Rule-based; it calls the platform&apos;s read-only tools as you and cites what they return. No language model.
      </p>
      {!event && <p className="text-[12px] text-muted">Select an event on the timeline to ask about it.</p>}
      {event && (
        <div className="space-y-2">
          <p className="text-[12px]">
            Selected: <span className="num">{event.id}</span> · {event.title} · <span className="num">{event.t.toFixed(2)} s</span>
          </p>
          <button className="btn btn-primary" disabled={ask.isPending} onClick={() => ask.mutate(event)}>
            {ask.isPending ? "Asking…" : "Explain this event"}
          </button>
          {ask.error && <p className="text-[12px] text-bad">{ask.error.message}</p>}
        </div>
      )}
      {call?.is_error && <p className="mt-2 text-[12px] text-bad">The tool refused: {String(call.result)}</p>}
      {ex && (
        <div className="mt-3 space-y-2" aria-live="polite" data-testid="explanation">
          {stale && <p className="text-[12px] text-warn">This explanation is for {ex.event.id}; the selection has changed.</p>}
          <ol className="space-y-2">
            {ex.findings.map((fd) => (
              <li key={fd.id} className="rounded-sm border border-line p-2 text-[12px]">
                <div className="mb-1 flex items-center gap-2">
                  <Badge tone={TONE[fd.severity]}>{fd.severity === "bad" ? "problem" : fd.severity === "warn" ? "caution" : "note"}</Badge>
                  <span className="num text-faint">{fd.id}</span>
                </div>
                <p>{fd.statement}</p>
                <ul className="mt-1.5 flex flex-wrap gap-1" aria-label={`Evidence for ${fd.id}`}>
                  {fd.evidence.map((e) => (
                    <li key={e} className="num rounded-sm bg-sunken px-1.5 py-0.5 text-[11px] text-muted">
                      {e}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
          <div>
            <h3 className="text-[12px] font-medium text-faint">Not known</h3>
            <ul className="list-disc pl-4 text-[12px] text-muted">
              {ex.not_known.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </div>
          <p className="text-[11px] text-faint">{ex.basis}</p>
        </div>
      )}
      {call && (
        <details className="mt-2 text-[12px]">
          <summary className="cursor-pointer text-muted">Tool call</summary>
          <dl className="num mt-1 grid grid-cols-[max-content_1fr] gap-x-2 break-all text-[11px]">
            <dt className="text-faint">tool</dt>
            <dd>{call.tool}</dd>
            <dt className="text-faint">as</dt>
            <dd>you (read-only: {String(call.read_only)})</dd>
            <dt className="text-faint">arguments</dt>
            <dd>{JSON.stringify(call.arguments)}</dd>
            <dt className="text-faint">answer</dt>
            <dd>{call.is_error ? "error" : `${ex?.findings.length ?? 0} findings, ${ex?.not_known.length ?? 0} not-known items`}</dd>
          </dl>
        </details>
      )}
    </section>
  );
}
