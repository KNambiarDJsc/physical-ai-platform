"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Notice, PageHeader, Panel } from "@/components/AppShell";
import { signInHref, useAuth } from "@/components/Identity";
import { getIdentity, setIdentity } from "@/lib/identity";

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" />
      <Panel title="Identity" className="max-w-xl">
        <Suspense>
          <IdentityPanel />
        </Suspense>
      </Panel>
    </>
  );
}

function IdentityPanel() {
  const auth = useAuth();
  const error = useSearchParams().get("auth_error");
  if (auth.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  const a = auth.data;
  if (!a || a.mode === "misconfigured") {
    return <Notice tone="bad">Sign-in is misconfigured on this server{a?.mode === "misconfigured" ? `: ${a.message}` : ""}.</Notice>;
  }
  if (a.mode === "oidc") {
    return (
      <>
        {error && <Notice tone="bad">Sign-in did not complete ({error}). Try again.</Notice>}
        {a.user ? (
          <>
            <p className="text-[13px] text-muted">
              Signed in as <span className="font-medium text-ink">{a.user.name}</span>{" "}
              <span className="num text-faint">({a.user.subject})</span>, through your identity provider.
            </p>
            <form method="post" action="/auth/logout" className="mt-3">
              <button className="btn" type="submit">
                Sign out
              </button>
            </form>
          </>
        ) : (
          <a className="btn btn-primary" href={signInHref("/")}>
            Sign in
          </a>
        )}
      </>
    );
  }
  return <DevIdentity />;
}

function DevIdentity() {
  const qc = useQueryClient();
  const [value, setValue] = useState("");
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => setCurrent(getIdentity()), []);
  return (
    <>
      <Notice tone="warn">
        Development identity: anyone can claim any subject. It works only when the API runs with PAP_AUTH_MODE=dev and
        is unavailable when PAP_ENV=production, where sign-in goes through your identity provider.
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
          className="field w-56"
        />
        <button className="btn btn-primary" type="submit">
          Sign in
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => {
            setIdentity(null);
            setCurrent(null);
            void qc.invalidateQueries();
          }}
        >
          Sign out
        </button>
      </form>
    </>
  );
}
