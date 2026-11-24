"use client";

import clsx from "clsx";
import {
  Activity,
  AlertTriangle,
  Bot,
  Box,
  Boxes,
  Cpu,
  FlaskConical,
  GitCompareArrows,
  LayoutDashboard,
  Monitor,
  Moon,
  PanelsTopLeft,
  Plug,
  Rocket,
  Route,
  Search,
  Settings,
  ShieldCheck,
  Sun,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getIdentity, IDENTITY_EVENT } from "@/lib/identity";
import { getTheme, setTheme, type Theme } from "@/lib/theme";
import { useAuth } from "./Identity";

type NavItem = { href: string; label: string; icon: LucideIcon; hint: string };

/** Only pages that exist. A module that is not built is not listed (DESIGN.md §1). */
const GROUPS: { label: string; items: NavItem[] }[] = [

  {
    label: "Projects",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard, hint: "Projects you can access" },
      { href: "/onboarding", label: "Get started", icon: Rocket, hint: "Workspace, environment, first verified run" },
      { href: "/fleet", label: "Fleet", icon: Boxes, hint: "Robots and outcome counts per release" },
    ],
  },
  {
    label: "Studio",
    items: [
      { href: "/twin", label: "Digital twin", icon: Box, hint: "Robot model, recordings and the event timeline" },
      { href: "/workflows", label: "Workflows", icon: Workflow, hint: "Device actions with a verification contract" },
      { href: "/journey", label: "Lab experiment", icon: Route, hint: "Guided path: configure, approve, run, investigate, export" },
      { href: "/experiments", label: "Experiments", icon: FlaskConical, hint: "Configure, approve and run simulation experiments" },
      { href: "/agent", label: "Agent", icon: Bot, hint: "Ask about runs and experiments; read-only, cites what it used" },
    ],
  },
  {
    label: "Runs",
    items: [
      { href: "/runs", label: "Run history", icon: Activity, hint: "Search workflow runs by environment, outcome and date" },
      { href: "/workbench", label: "Workbench", icon: PanelsTopLeft, hint: "Run workflows, watch instruments, read verdicts" },
      { href: "/releases", label: "Releases", icon: GitCompareArrows, hint: "Baseline vs candidate comparisons" },
      { href: "/evidence", label: "Evidence", icon: Activity, hint: "Stored files and their digests" },
      { href: "/verification", label: "Verification", icon: ShieldCheck, hint: "Reported vs independently verified" },
      { href: "/incidents", label: "Incidents", icon: AlertTriangle, hint: "Failures the engine grouped" },
    ],
  },
  {
    label: "Integrations",
    items: [
      { href: "/hardware", label: "Hardware Hub", icon: Cpu, hint: "Environments, devices and capabilities" },
      { href: "/integrations", label: "Integrations", icon: Plug, hint: "API, credentials, engine build" },
    ],
  },
  {
    label: "Settings",
    items: [
      { href: "/settings", label: "Settings", icon: Settings, hint: "Identity and sign-in" },
    ],
  },
];
const ALL = GROUPS.flatMap((g) => g.items);

const PRIMARY: NavItem[] = [
  { href: "/", label: "Projects", icon: LayoutDashboard, hint: "Projects and workspaces" },
  { href: "/twin", label: "Studio", icon: Box, hint: "Explore, execute and investigate" },
  { href: "/runs", label: "Runs", icon: Activity, hint: "Run history and release evidence" },
  { href: "/hardware", label: "Integrations", icon: Cpu, hint: "Environments and connected services" },
  { href: "/settings", label: "Settings", icon: Settings, hint: "Identity and workspace settings" },
];

function primaryActive(path: string, href: string): boolean {
  if (href === "/") return path === "/" || path === "/onboarding" || path === "/fleet" || /^\/o\/[^/]+\/p\/[^/]+$/.test(path);
  if (href === "/twin") return ["/twin", "/workflows", "/journey", "/experiments", "/agent"].some((p) => path.startsWith(p));
  if (href === "/runs") return ["/runs", "/workbench", "/releases", "/evidence", "/verification", "/incidents"].some((p) => path.startsWith(p)) || /\/e\//.test(path);
  if (href === "/hardware") return path.startsWith("/hardware") || path.startsWith("/integrations");
  return path.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [palette, setPalette] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="studio-shell-nav sticky top-0 z-30 border-b border-line bg-panel">
        <div className="flex min-h-14 flex-wrap items-center gap-3 px-3 sm:flex-nowrap sm:px-5">
          <Link href="/" className="flex shrink-0 items-center gap-2.5 rounded-sm">
            <span aria-hidden className="grid size-7 place-items-center rounded-[5px] border border-line bg-bg font-mono text-[11px] font-semibold text-accent">PA</span>
            <span className="hidden text-[13px] font-semibold tracking-[-0.02em] sm:inline">Physical AI Studio</span>
          </Link>
          <nav aria-label="Main" className="order-3 -mx-3 flex basis-full min-w-0 gap-1 overflow-x-auto border-t border-line px-2 py-1.5 sm:order-none sm:mx-0 sm:min-w-fit sm:basis-auto sm:flex-initial sm:border-0 sm:px-0 sm:py-0 sm:pl-5">
            {PRIMARY.map(({ href, label, icon: Icon }) => {
              const on = primaryActive(path, href);
              return <Link key={href} href={href} aria-current={on ? "page" : undefined} title={label} className={clsx("flex h-9 shrink-0 items-center gap-2 rounded-[5px] px-2.5 text-[12px] font-medium transition-colors sm:px-3 sm:text-[13px]", on ? "bg-selected text-ink" : "text-muted hover:bg-hover hover:text-ink")}>
                <Icon size={15} strokeWidth={1.8} aria-hidden className={on ? "text-accent" : undefined} />
                <span className="hidden max-sm:inline md:inline">{label}</span>
              </Link>;
            })}
          </nav>
          <div className="order-2 ml-auto flex shrink-0 items-center gap-1.5 sm:order-none">
            <button type="button" onClick={() => setPalette(true)} className="btn h-8 text-muted" aria-haspopup="dialog" aria-label="Go to… Ctrl K" title="Open the page finder">
              <Search size={14} aria-hidden />
              <span className="hidden font-normal sm:inline">Go to…</span>
              <span className="kbd hidden sm:inline-flex">Ctrl K</span>
            </button>
            <ThemeSwitch />
            <WhoAmI />
          </div>
        </div>
      </header>
      <div className="flex min-w-0 flex-1 flex-col">
        <main className="min-w-0 flex-1 px-4 py-5 md:px-7">
          <div key={path} className="reveal">
            {children}
          </div>
        </main>
      </div>
      {palette && <CommandPalette onClose={() => setPalette(false)} />}
    </div>
  );
}

function ThemeSwitch() {
  const [theme, set] = useState<Theme>("system");
  useEffect(() => set(getTheme()), []);
  const next: Record<Theme, Theme> = { system: "dark", dark: "light", light: "system" };
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  return (
    <button
      type="button"
      className="btn size-7 justify-center p-0 text-muted"
      aria-label={`Theme: ${theme}. Switch to ${next[theme]}`}
      title={`Theme: ${theme}`}
      onClick={() => {
        setTheme(next[theme]);
        set(next[theme]);
      }}
    >
      <Icon size={14} aria-hidden />
    </button>
  );
}

function WhoAmI() {
  const auth = useAuth();
  const [dev, setDev] = useState<string | null>(null);
  useEffect(() => {
    const read = () => setDev(getIdentity());
    read();
    window.addEventListener(IDENTITY_EVENT, read);
    return () => window.removeEventListener(IDENTITY_EVENT, read);
  }, []);
  const a = auth.data;
  const who = a?.mode === "oidc" ? (a.user?.name ?? null) : a?.mode === "dev" ? (dev?.replace(/^dev:/, "") ?? null) : null;
  if (auth.isLoading) return null;
  return who ? (
    <Link href="/settings" className="flex h-7 max-w-40 items-center gap-1.5 rounded-[5px] px-1.5 text-[12px] text-muted hover:bg-sunken hover:text-ink" title="Signed in. Change in Settings">
      <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-ok" />
      <span className="truncate num">{who}</span>
    </Link>
  ) : (
    <Link href="/settings" className="btn h-7 text-muted">
      Signed out
    </Link>
  );
}

function CommandPalette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const results = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? ALL.filter((i) => i.label.toLowerCase().includes(s) || i.hint.toLowerCase().includes(s)) : ALL;
  }, [q]);
  // Focus moves into the palette and returns to wherever it was when the palette closes.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => before?.focus?.();
  }, []);
  useEffect(() => setSel(0), [q]);
  const go = (i: NavItem | undefined) => {
    if (!i) return;
    onClose();
    router.push(i.href);
  };
  return (
    <div className="scrim-enter fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 pt-[14vh]" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="dialog-enter w-full max-w-lg overflow-hidden rounded-md border border-line bg-panel shadow-2xl shadow-black/40"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-line px-3">
          <Search size={14} aria-hidden className="text-faint" />
          <input
            ref={input}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
              else if (e.key === "Tab") e.preventDefault(); // the input is the dialog's only stop: Tab must not reach the page behind
              else if (e.key === "ArrowDown") {
                e.preventDefault();
                setSel((s) => Math.min(s + 1, results.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setSel((s) => Math.max(s - 1, 0));
              } else if (e.key === "Enter") go(results[sel]);
            }}
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-activedescendant={results[sel] ? `palette-option-${sel}` : undefined}
            aria-label="Go to page"
            placeholder="Go to page…"
            className="h-11 flex-1 bg-transparent text-[14px] outline-none placeholder:text-faint"
          />
          <span className="kbd">Esc</span>
        </div>
        {results.length === 0 && (
          <p role="status" className="px-3.5 py-3 text-[13px] text-muted">
            No page matches “{q}”.
          </p>
        )}
        <ul id="palette-list" role="listbox" aria-label="Pages" className={clsx("max-h-80 overflow-y-auto p-1.5", results.length === 0 && "hidden")}>
          {results.map((i, n) => (
            <li
              key={i.href}
              id={`palette-option-${n}`}
              role="option"
              aria-selected={n === sel}
              onMouseEnter={() => setSel(n)}
              onClick={() => go(i)}
              className={clsx("flex cursor-pointer items-center gap-2.5 rounded-[5px] px-2 py-1.5 text-[13px]", n === sel ? "bg-sunken text-ink" : "text-muted")}
            >
              <i.icon size={14} strokeWidth={1.75} aria-hidden />
              <span className="text-ink">{i.label}</span>
              <span className="truncate text-faint">{i.hint}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3 border-b border-line pb-4">
      <div className="min-w-0">
        <h1 className="text-[clamp(1.3rem,2vw,1.8rem)] font-semibold leading-tight tracking-[-0.035em]">{title}</h1>
        {subtitle && <div className="mt-0.5 text-[13px] text-muted">{subtitle}</div>}
      </div>
      {actions}
    </header>
  );
}

export function Panel({ title, children, className }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("rounded-md border border-line bg-panel", className)}>
      {title && <h2 className="border-b border-line px-4 py-2 text-[13px] font-medium">{title}</h2>}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Notice({ tone, children }: { tone: "warn" | "bad" | "info"; children: ReactNode }) {
  const cls = {
    warn: "border-warn/35 bg-warn-soft text-warn",
    bad: "border-bad/35 bg-bad-soft text-bad",
    info: "border-line bg-sunken text-muted",
  }[tone];
  return (
    <div role={tone === "info" ? "status" : "alert"} className={clsx("rounded-[5px] border px-3 py-2 text-[13px]", cls)}>
      {children}
    </div>
  );
}
