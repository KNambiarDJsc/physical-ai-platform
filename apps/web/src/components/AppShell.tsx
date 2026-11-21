"use client";

import clsx from "clsx";
import {
  Activity,
  AlertTriangle,
  Boxes,
  ChevronRight,
  Cpu,
  GitCompareArrows,
  LayoutDashboard,
  Monitor,
  Moon,
  PanelsTopLeft,
  Plug,
  Rocket,
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
    label: "Lab automation",
    items: [
      { href: "/onboarding", label: "Get started", icon: Rocket, hint: "Workspace, environment, first verified run" },
      { href: "/workbench", label: "Workbench", icon: PanelsTopLeft, hint: "Run workflows, watch instruments, read verdicts" },
      { href: "/hardware", label: "Hardware Hub", icon: Cpu, hint: "Environments, devices and capabilities" },
      { href: "/workflows", label: "Workflows", icon: Workflow, hint: "Device actions with a verification contract" },
    ],
  },
  {
    label: "Release intelligence",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard, hint: "Projects you can access" },
      { href: "/releases", label: "Releases", icon: GitCompareArrows, hint: "Baseline vs candidate comparisons" },
      { href: "/verification", label: "Verification", icon: ShieldCheck, hint: "Reported vs independently verified" },
      { href: "/incidents", label: "Incidents", icon: AlertTriangle, hint: "Failures the engine grouped" },
      { href: "/evidence", label: "Evidence", icon: Activity, hint: "Stored files and their digests" },
    ],
  },
  {
    label: "Operations",
    items: [{ href: "/fleet", label: "Fleet", icon: Boxes, hint: "Robots and outcome counts per release" }],
  },
  {
    label: "Workspace",
    items: [
      { href: "/integrations", label: "Integrations", icon: Plug, hint: "API, credentials, engine build" },
      { href: "/settings", label: "Settings", icon: Settings, hint: "Identity and sign-in" },
    ],
  },
];
const ALL = GROUPS.flatMap((g) => g.items);

function isActive(path: string, href: string): boolean {
  if (href === "/") return path === "/";
  return path.startsWith(href) || (href === "/releases" && path.startsWith("/o/"));
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
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav
        aria-label="Main"
        className="shrink-0 border-b border-line bg-panel md:sticky md:top-0 md:flex md:h-screen md:w-56 md:flex-col md:border-r md:border-b-0"
      >
        <div className="hidden items-center gap-2.5 px-4 pb-4 pt-3.5 md:flex">
          <span aria-hidden className="grid size-6 place-items-center rounded-[5px] border border-line bg-bg font-mono text-[11px] font-semibold text-accent">
            RP
          </span>
          <div className="min-w-0 leading-tight">
            <div className="truncate text-[13px] font-semibold">Reliability Platform</div>
            <div className="truncate text-[11px] text-faint" title="Commands go only to simulated devices; physical devices are read, never commanded">
              Self-hosted · no hardware control
            </div>
          </div>
        </div>
        <div className="flex gap-0.5 overflow-x-auto px-2 py-1.5 md:block md:space-y-4 md:overflow-visible md:py-0">
          {GROUPS.map((g) => (
            <div key={g.label} className="flex gap-0.5 md:block">
              <div className="hidden px-2 pb-1 text-[11px] font-medium text-faint md:block">{g.label}</div>
              <ul className="flex gap-0.5 md:block md:space-y-px">
                {g.items.map(({ href, label, icon: Icon }) => {
                  const on = isActive(path, href);
                  return (
                    <li key={href}>
                      <Link
                        href={href}
                        aria-current={on ? "page" : undefined}
                        className={clsx(
                          "relative flex h-7 items-center gap-2 whitespace-nowrap rounded-[5px] px-2 text-[13px] transition-colors duration-150",
                          on ? "bg-sunken font-medium text-ink" : "text-muted hover:bg-sunken hover:text-ink",
                        )}
                      >
                        {on && <span aria-hidden className="absolute inset-y-1.5 left-0 hidden w-0.5 rounded-full bg-accent md:block" />}
                        <Icon size={14} strokeWidth={1.75} aria-hidden className={on ? "text-accent" : undefined} />
                        <span>{label}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-auto hidden border-t border-line px-4 py-2.5 text-[11px] text-faint md:block">
          Engine: OpenMHS (pinned)
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar path={path} onPalette={() => setPalette(true)} />
        <main className="min-w-0 flex-1 px-4 py-5 md:px-7">{children}</main>
      </div>
      {palette && <CommandPalette onClose={() => setPalette(false)} />}
    </div>
  );
}

/** Breadcrumb from the URL only: slugs and short ids, nothing fetched and nothing inferred. */
function crumbs(path: string): { label: string; href?: string; mono?: boolean }[] {
  const m = path.match(/^\/o\/([^/]+)\/p\/([^/]+)(?:\/e\/([^/]+)(\/episodes)?)?/);
  if (m) {
    const [, org = "", project = "", evaluation, episodes] = m;
    const out: { label: string; href?: string; mono?: boolean }[] = [
      { label: "Releases", href: "/releases" },
      { label: org },
      { label: project, href: `/o/${org}/p/${project}` },
    ];
    if (evaluation) out.push({ label: `evaluation ${evaluation.slice(0, 8)}`, href: `/o/${org}/p/${project}/e/${evaluation}`, mono: true });
    if (episodes) out.push({ label: "Episodes" });
    return out;
  }
  const item = ALL.find((i) => isActive(path, i.href));
  return [{ label: item?.label ?? "Page" }];
}

function TopBar({ path, onPalette }: { path: string; onPalette: () => void }) {
  const items = crumbs(path);
  return (
    <header className="sticky top-0 z-20 flex h-11 items-center gap-3 border-b border-line bg-bg/95 px-4 backdrop-blur-[2px] md:px-7">
      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex min-w-0 items-center gap-1 text-[13px]">
          {items.map((c, i) => {
            const last = i === items.length - 1;
            return (
              <li key={i} className={clsx("flex min-w-0 items-center gap-1", c.mono && "num", last ? "text-ink" : "text-muted")}>
                {i > 0 && <ChevronRight size={13} aria-hidden className="shrink-0 text-faint" />}
                {c.href && !last ? (
                  <Link href={c.href} className="truncate hover:text-ink">
                    {c.label}
                  </Link>
                ) : (
                  <span className="truncate" aria-current={last ? "page" : undefined}>
                    {c.label}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
      <button type="button" onClick={onPalette} className="btn hidden h-7 text-muted sm:inline-flex" aria-haspopup="dialog" title="Open the command palette">
        <Search size={13} aria-hidden />
        <span className="font-normal">Go to…</span>
        <span className="kbd">Ctrl K</span>
      </button>
      <ThemeSwitch />
      <WhoAmI />
    </header>
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
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 pt-[14vh]" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full max-w-lg overflow-hidden rounded-md border border-line bg-panel shadow-2xl shadow-black/40"
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
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-[15px] font-semibold tracking-[-0.01em]">{title}</h1>
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
