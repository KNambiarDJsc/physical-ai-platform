"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { ReactNode } from "react";
import { api } from "@/lib/api/client";
import { getIdentity } from "@/lib/identity";
import { Notice } from "./AppShell";

export type Me = { kind: string; subject?: string; organizations: { slug: string; role: string }[] };

export function useMe() {
  return useQuery({ queryKey: ["me", getIdentity()], queryFn: () => api<Me>("/api/v1/me"), enabled: !!getIdentity() });
}

/** Renders children only for a signed-in caller; otherwise says how to sign in. */
export function RequireIdentity({ children }: { children: ReactNode }) {
  if (typeof window !== "undefined" && !getIdentity()) {
    return (
      <Notice tone="info">
        Not signed in. Choose a development identity in <Link className="underline" href="/settings">Settings</Link>.
      </Notice>
    );
  }
  return <>{children}</>;
}
