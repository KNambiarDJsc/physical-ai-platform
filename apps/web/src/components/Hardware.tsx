"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { api, orgPath, type CatalogEntry, type Capability, type Device, type Discovery, type PropertyRead } from "@/lib/api/client";
import { shortDigest } from "@/lib/format";
import { Notice, PageHeader, Panel } from "./AppShell";
import { RequireIdentity } from "./Identity";
import { Split } from "./Split";
import { Badge, Table, Td, Time } from "./ui";
import { OrgSelect, useDevices, useEnvironments, useOrg } from "./Workspace";

export function KindBadge({ kind }: { kind: string }) {
  return kind === "simulated" ? <Badge tone="warn">SIMULATED</Badge> : <Badge tone="neutral">PHYSICAL · READ ONLY</Badge>;
}

export function HardwareView() {
  return (
    <RequireIdentity>
      <Hardware />
    </RequireIdentity>
  );
}

function Hardware() {
  const { me, orgs, org, role, select } = useOrg();
  if (me.isLoading) return <p className="text-[13px] text-muted">Loading…</p>;
  return (
    <>
      <PageHeader
        title="Hardware Hub"
        subtitle="Environments your operator offers, the devices discovered in them, and what each device can do."
        actions={<OrgSelect orgs={orgs} org={org} select={select} />}
      />
      {!org ? (
        <Notice tone="info">You have no workspace yet. Start on the Get started page.</Notice>
      ) : (
        <div className="space-y-4">
          <Environments org={org} admin={role === "admin"} canDiscover={role !== "viewer"} />
          <DeviceBrowser org={org} />
        </div>
      )}
    </>
  );
}

export function useCatalog() {
  return useQuery({ queryKey: ["catalog"], queryFn: () => api<CatalogEntry[]>("/api/v1/environment-catalog") });
}

export function useDiscover(org: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (env: string) => api<Discovery>(`${orgPath(org)}/environments/${env}/discover`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["environments", org] });
      void qc.invalidateQueries({ queryKey: ["devices", org] });
    },
  });
}

function Environments({ org, admin, canDiscover }: { org: string; admin: boolean; canDiscover: boolean }) {
  const qc = useQueryClient();
  const envs = useEnvironments(org);
  const catalog = useCatalog();
  const discover = useDiscover(org);
  const [choice, setChoice] = useState("");
  const connect = useMutation({
    mutationFn: (key: string) => api(`${orgPath(org)}/environments`, { method: "POST", body: JSON.stringify({ config_key: key }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["environments", org] }),
  });
  const connected = new Set((envs.data ?? []).map((e) => e.config_key));
  const offer = (catalog.data ?? []).filter((c) => !connected.has(c.key));
  return (
    <Panel title="Environments">
      {envs.error && <Notice tone="bad">{envs.error.message}</Notice>}
      {envs.data && envs.data.length === 0 && <p className="mb-3 text-[13px] text-muted">No environment connected to this workspace yet.</p>}
      {envs.data && envs.data.length > 0 && (
        <Table head={["Environment", "Kind", "Adapter", "Endpoint", "Devices", "Last discovery", ""]} caption="Connected environments">
          {envs.data.map((e) => (
            <tr key={e.id}>
              <Td>
                <span className="font-medium">{e.name}</span> <span className="num text-faint">{e.slug}</span>
              </Td>
              <Td>
                <KindBadge kind={e.kind} />
              </Td>
              <Td className="num text-muted">{e.adapter}</Td>
              <Td className="num text-muted">{e.available ? e.endpoint : <Badge tone="bad">withdrawn by the operator</Badge>}</Td>
              <Td num>{e.devices}</Td>
              <Td>
                <Time iso={e.last_discovered_at} />
              </Td>
              <Td>
                {canDiscover && e.available && (
                  <button className="btn" disabled={discover.isPending} onClick={() => discover.mutate(e.slug)}>
                    {discover.isPending && discover.variables === e.slug ? "Discovering…" : "Discover devices"}
                  </button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      )}
      {discover.error && <div className="mt-3"><Notice tone="bad">Discovery failed: {discover.error.message}</Notice></div>}
      {discover.data && (
        <p role="status" className="mt-3 text-[13px] text-muted">
          Found {discover.data.found} device{discover.data.found === 1 ? "" : "s"} in {discover.data.environment}: {discover.data.new} new,{" "}
          {discover.data.changed} changed, {discover.data.missing} missing.
        </p>
      )}
      {admin && offer.length > 0 && (
        <form
          className="mt-4 flex flex-wrap items-end gap-2 border-t border-line pt-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (choice || offer[0]) connect.mutate(choice || offer[0]!.key);
          }}
        >
          <label className="text-[13px]">
            <span className="mb-1 block text-muted">Connect an environment</span>
            <select className="field min-w-64" value={choice || offer[0]?.key} onChange={(e) => setChoice(e.target.value)}>
              {offer.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.name} ({c.kind})
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-primary" type="submit" disabled={connect.isPending}>
            Connect
          </button>
          {connect.error && <Notice tone="bad">{connect.error.message}</Notice>}
          <p className="w-full text-[12px] text-faint">
            Only environments your operator configured are offered. Physical environments can be discovered and read, never commanded.
          </p>
        </form>
      )}
      {catalog.data && catalog.data.length === 0 && (
        <p className="mt-3 text-[13px] text-muted">This installation offers no environments (PAP_ENVIRONMENTS is empty).</p>
      )}
    </Panel>
  );
}

function DeviceBrowser({ org }: { org: string }) {
  const devices = useDevices(org);
  const [selected, setSelected] = useState<string | null>(null);
  if (devices.isLoading) return <p className="text-[13px] text-muted">Loading devices…</p>;
  if (devices.error) return <Notice tone="bad">{devices.error.message}</Notice>;
  const list = devices.data ?? [];
  if (list.length === 0) return <Notice tone="info">No devices yet. Connect an environment and discover its devices.</Notice>;
  const current = list.find((d) => d.id === selected) ?? list[0]!;
  const byEnv = new Map<string, Device[]>();
  for (const d of list) byEnv.set(d.environment, [...(byEnv.get(d.environment) ?? []), d]);
  return (
    <section aria-label="Devices" className="overflow-hidden rounded-md border border-line bg-panel">
      <Split
        side="start"
        label="Resize the device list"
        initial={240}
        min={180}
        max={420}
        className="h-[560px]"
        pane={
          <nav aria-label="Devices" className="p-2">
            {[...byEnv.entries()].map(([env, ds]) => (
              <div key={env} className="mb-3">
                <div className="px-2 pb-1 text-[11px] font-medium text-faint">{env}</div>
                <ul className="space-y-px">
                  {ds.map((d) => (
                    <li key={d.id}>
                      <button
                        type="button"
                        aria-current={d.id === current.id ? "true" : undefined}
                        onClick={() => setSelected(d.id)}
                        className={clsx(
                          "flex w-full items-center gap-2 rounded-[5px] px-2 py-1.5 text-left text-[13px]",
                          d.id === current.id ? "bg-sunken text-ink" : "text-muted hover:bg-sunken hover:text-ink",
                        )}
                      >
                        <span aria-hidden className={clsx("size-1.5 shrink-0 rounded-full", d.present ? "bg-ok" : "bg-faint")} />
                        <span className="truncate">{d.key}</span>
                        {!d.present && <span className="ml-auto text-[11px] text-faint">missing</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        }
      >
        <Inspector org={org} device={current} />
      </Split>
    </section>
  );
}

function Inspector({ org, device }: { org: string; device: Device }) {
  const props = device.capabilities.filter((c) => c.kind === "property");
  const actions = device.capabilities.filter((c) => c.kind === "action");
  return (
    <div className="p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-[14px] font-semibold">{device.title}</h2>
        <KindBadge kind={device.environment_kind} />
        {device.declares_simulated && <Badge tone="neutral">declares simulated</Badge>}
        {!device.present && <Badge tone="bad">not found at the last discovery</Badge>}
      </div>
      {device.description && <p className="mb-3 max-w-3xl text-[13px] text-muted">{device.description}</p>}
      <dl className="mb-4 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-[12px]">
        <dt className="text-muted">Key</dt>
        <dd className="num">{device.key}</dd>
        <dt className="text-muted">Protocol</dt>
        <dd className="num">{device.protocol} (W3C Thing Description)</dd>
        <dt className="text-muted">Description digest</dt>
        <dd className="num" title={device.td_sha256}>
          sha256:{shortDigest(device.td_sha256)}
        </dd>
        <dt className="text-muted">Updated</dt>
        <dd>
          <Time iso={device.updated_at} />
        </dd>
      </dl>
      <h3 className="mb-1 text-[13px] font-medium">Properties ({props.length})</h3>
      <Table head={["Property", "Type", "Access", "Live value", ""]} caption={`Properties of ${device.key}`}>
        {props.map((p) => (
          <PropertyRow key={p.name} org={org} device={device} cap={p} />
        ))}
      </Table>
      <h3 className="mb-1 mt-5 text-[13px] font-medium">Actions ({actions.length})</h3>
      <ul className="divide-y divide-line rounded-md border border-line">
        {actions.map((a) => (
          <li key={a.name} className="px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="num font-medium">{a.name}</span>
              <span className="text-[13px] text-muted">{a.title}</span>
              {a.idempotency_key && (
                <Badge tone="ok" >idempotent · {a.idempotency_key}</Badge>
              )}
            </div>
            <InputSummary cap={a} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function schemaType(s: Record<string, unknown> | null | undefined): string {
  if (!s) return "—";
  const t = s.type;
  const bits = [String(t ?? (s.oneOf || s.anyOf ? "union" : "any"))];
  if (s.exclusiveMinimum !== undefined) bits.push(`> ${String(s.exclusiveMinimum)}`);
  if (s.minimum !== undefined) bits.push(`≥ ${String(s.minimum)}`);
  if (s.maximum !== undefined) bits.push(`≤ ${String(s.maximum)}`);
  return bits.join(" ");
}

function InputSummary({ cap }: { cap: Capability }) {
  const props = (cap.input_schema?.properties ?? {}) as Record<string, Record<string, unknown>>;
  const required = new Set((cap.input_schema?.required ?? []) as string[]);
  const names = Object.keys(props);
  if (names.length === 0) return <div className="mt-1 text-[12px] text-faint">No input.</div>;
  return (
    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[12px]">
      {names.map((n) => (
        <span key={n} className="num text-muted">
          {n}
          {required.has(n) ? "" : "?"}: {schemaType(props[n])}
        </span>
      ))}
    </div>
  );
}

function PropertyRow({ org, device, cap }: { org: string; device: Device; cap: Capability }) {
  const read = useMutation({
    mutationFn: () => api<PropertyRead>(`${orgPath(org)}/devices/${device.id}/properties/${cap.name}`),
  });
  return (
    <tr>
      <Td>
        <span className="num">{cap.name}</span>
      </Td>
      <Td className="num text-muted">{schemaType(cap.data_schema)}</Td>
      <Td className="text-muted">{cap.read_only ? "read" : "read, write"}</Td>
      <Td className="num">
        {read.data ? (
          <span title={`read ${read.data.read_at}`}>{JSON.stringify(read.data.value)}</span>
        ) : read.error ? (
          <span className="text-bad">{read.error.message}</span>
        ) : (
          <span className="text-faint">—</span>
        )}
      </Td>
      <Td>
        <button className="btn py-0.5" type="button" onClick={() => read.mutate()} disabled={read.isPending} aria-label={`Read ${cap.name}`}>
          Read
        </button>
      </Td>
    </tr>
  );
}
