"use client";

import clsx from "clsx";
import {
  Activity,
  AlertTriangle,
  Boxes,
  GitCompareArrows,
  LayoutDashboard,
  Plug,
  Settings,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard, ready: true },
  { href: "/releases", label: "Releases", icon: GitCompareArrows, ready: true },
  { href: "/fleet", label: "Fleet", icon: Boxes, ready: true },
  { href: "/incidents", label: "Incidents", icon: AlertTriangle, ready: true },
  { href: "/verification", label: "Verification", icon: ShieldCheck, ready: true },
  { href: "/evidence", label: "Evidence", icon: Activity, ready: true },
  { href: "/integrations", label: "Integrations", icon: Plug, ready: true },
  { href: "/settings", label: "Settings", icon: Settings, ready: true },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const active = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href) || (href === "/releases" && path.startsWith("/o/"));
  return (
    <div className="flex min-h-screen">
      <nav aria-label="Main" className="hidden w-56 shrink-0 border-r border-line bg-panel md:block">
        <div className="px-4 pb-3 pt-4">
          <div className="text-[13px] font-semibold tracking-tight">Reliability Platform</div>
          <div className="text-xs text-faint">Release Intelligence</div>
        </div>
        <ul className="space-y-0.5 px-2">
          {NAV.map(({ href, label, icon: Icon, ready }) => (
            <li key={href}>
              <Link
                href={href}
                aria-current={active(href) ? "page" : undefined}
                className={clsx(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px]",
                  active(href) ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-sunken hover:text-ink",
                )}
              >
                <Icon size={15} aria-hidden />
                <span className="flex-1">{label}</span>
                {!ready && <span className="text-[10px] uppercase tracking-wide text-faint">Soon</span>}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <main className="min-w-0 flex-1 px-4 py-5 md:px-8">{children}</main>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {subtitle && <div className="mt-0.5 text-[13px] text-muted">{subtitle}</div>}
      </div>
      {actions}
    </header>
  );
}

export function Panel({ title, children, className }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("rounded-lg border border-line bg-panel", className)}>
      {title && <h2 className="border-b border-line px-4 py-2.5 text-[13px] font-semibold">{title}</h2>}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Notice({ tone, children }: { tone: "warn" | "bad" | "info"; children: ReactNode }) {
  const cls = {
    warn: "border-warn/40 bg-warn-soft text-warn",
    bad: "border-bad/40 bg-bad-soft text-bad",
    info: "border-line bg-sunken text-muted",
  }[tone];
  return (
    <div role={tone === "info" ? "status" : "alert"} className={clsx("rounded-md border px-3 py-2 text-[13px]", cls)}>
      {children}
    </div>
  );
}
