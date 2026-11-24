"use client";
import type { AgentFocus } from "./Agent";
import dynamic from "next/dynamic";
import { useState } from "react";

const Agent = dynamic(() => import("./Agent").then((module) => module.Agent), {
  loading: () => <p role="status">Loading investigation tools…</p>,
});

export function InvestigationAgent({ question, workspace, focus }: { question: string; workspace: string; focus: AgentFocus }) {
  const [loaded, setLoaded] = useState(false);
  return (
    <details className="border-y border-line bg-panel p-3" onToggle={(event) => event.currentTarget.open && setLoaded(true)}>
      <summary className="cursor-pointer text-sm font-semibold text-accent">Investigate with Engineering Agent</summary>
      {loaded && <div className="mt-3"><Agent key={workspace + question} initialQuestion={question} workspace={workspace} focus={focus} /></div>}
    </details>
  );
}
