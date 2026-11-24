"use client";

import Link from "next/link";
import { Activity, FlaskConical, ScanSearch } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";

const modes = [
  { label: "Explore", path: "/twin", icon: ScanSearch },
  { label: "Execute", path: "/experiments", icon: FlaskConical },
  { label: "Investigate", path: "/workbench", icon: Activity },
];

export function StudioModes({ org }: { org: string }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const active = pathname === "/twin" ? "/twin" : ["/experiments", "/workflows", "/journey"].includes(pathname) ? "/experiments" : "/workbench";
  return (
    <nav aria-label="Studio modes" className="flex items-center gap-1 border-b border-line bg-panel px-4 py-1.5 md:px-7">
      <span className="mr-2 hidden text-[11px] font-medium text-faint sm:inline">Workspace</span>
      {modes.map(({ label, path, icon: Icon }) => {
        const current = active === path;
        const query = new URLSearchParams(current ? params.toString() : "");
        query.set("org", org);
        const project = params.get("project");
        if (project) query.set("project", project);
        return (
          <Link key={path} href={`${path}?${query}`} aria-current={current ? "page" : undefined}
            className={`flex min-h-8 items-center gap-1.5 rounded px-3 py-1.5 text-[12px] font-medium transition-colors sm:text-[13px] ${current ? "bg-accent-soft text-accent" : "text-muted hover:bg-hover hover:text-ink"}`}>
            <Icon size={14} aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
