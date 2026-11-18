"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Notice, PageHeader, Panel } from "@/components/AppShell";
import { getIdentity, setIdentity } from "@/lib/identity";

export default function SettingsPage() {
  const qc = useQueryClient();
  const [value, setValue] = useState("");
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => setCurrent(getIdentity()), []);
  return (
    <>
      <PageHeader title="Settings" />
      <Panel title="Identity" className="max-w-xl">
        <Notice tone="warn">
          Development identity: works only when the API runs with PAP_AUTH_MODE=dev. Sign-in through your identity
          provider (OIDC) is not built into the web app yet.
        </Notice>
        <p className="mt-3 text-[13px] text-muted">
          Signed in as: <span className="num text-ink">{current ?? "nobody"}</span>
        </p>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setIdentity(value.trim() || null);
            setCurrent(getIdentity());
            void qc.invalidateQueries();
          }}
        >
          <label className="sr-only" htmlFor="subject">
            Subject
          </label>
          <input
            id="subject"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="subject, e.g. alice"
            className="w-56 rounded-md border border-line bg-panel px-2 py-1.5 text-[13px]"
          />
          <button className="rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-white" type="submit">
            Sign in
          </button>
          <button
            type="button"
            className="rounded-md border border-line px-3 py-1.5 text-[13px]"
            onClick={() => {
              setIdentity(null);
              setCurrent(null);
              void qc.invalidateQueries();
            }}
          >
            Sign out
          </button>
        </form>
      </Panel>
    </>
  );
}
