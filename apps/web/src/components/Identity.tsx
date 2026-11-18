"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { api } from "@/lib/api/client";
import { getIdentity } from "@/lib/identity";
import { Notice } from "./AppShell";

export type Me = { kind: string; subject?: string; organizations: { slug: string; role: string }[] };
export type AuthState =
  | { mode: "dev"; user: null }
  | { mode: "oidc"; user: { subject: string; name: string; expires_at: number } | null }
  | { mode: "misconfigured"; user: null; message: string };

/** How this web server signs people in, and who is signed in. Holds no token: the session cookie is HttpOnly. */
export function useAuth() {
  return useQuery({
    queryKey: ["auth-session"],
    queryFn: async () => (await (await fetch("/auth/session", { cache: "no-store" })).json()) as AuthState,
    staleTime: 30_000,
  });
}

export function signedIn(auth: AuthState | undefined): boolean {
  if (!auth) return false;
  return auth.mode === "oidc" ? !!auth.user : auth.mode === "dev" && !!getIdentity();
}

export function useMe() {
  const auth = useAuth();
  const key = auth.data?.mode === "oidc" ? auth.data.user?.subject : getIdentity();
  return useQuery({ queryKey: ["me", key], queryFn: () => api<Me>("/api/v1/me"), enabled: signedIn(auth.data) });
}

export function signInHref(returnTo: string): string {
  return `/auth/login?return_to=${encodeURIComponent(returnTo)}`;
}

/** Renders children only for a signed-in caller; otherwise says how to sign in. */
export function RequireIdentity({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const path = usePathname();
  if (auth.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  const a = auth.data;
  if (!a || a.mode === "misconfigured") {
    return <Notice tone="bad">Sign-in is misconfigured on this server{a?.mode === "misconfigured" ? `: ${a.message}` : ""}.</Notice>;
  }
  if (a.mode === "oidc" && !a.user) {
    return (
      <Notice tone="info">
        Not signed in.{" "}
        <a className="font-medium underline" href={signInHref(path)}>
          Sign in
        </a>{" "}
        with your organization&apos;s identity provider.
      </Notice>
    );
  }
  if (a.mode === "dev" && typeof window !== "undefined" && !getIdentity()) {
    return (
      <Notice tone="info">
        Not signed in. Choose a development identity in <Link className="underline" href="/settings">Settings</Link>.
      </Notice>
    );
  }
  return <>{children}</>;
}
