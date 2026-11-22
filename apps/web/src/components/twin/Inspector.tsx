"use client";

import clsx from "clsx";
import { useState } from "react";
import { drivenJoints, linkDetail, type Sample, type Structure, type Track } from "@/lib/twin";
import { Badge } from "../ui";

type Tab = "links" | "joints" | "controllers" | "sensors";
const TABS: { id: Tab; label: string }[] = [
  { id: "links", label: "Links" },
  { id: "joints", label: "Joints" },
  { id: "controllers", label: "Controllers" },
  { id: "sensors", label: "Sensors" },
];

const f = (n: number | null | undefined, digits = 3) => (n === null || n === undefined ? "—" : n.toFixed(digits));

/** What the model (the URDF) says about a link, a joint, a controller or a sensor, with the current joint value. */
export function Inspector({
  structure,
  sample,
  track,
  selected,
  onSelect,
  modelName,
}: {
  structure: Structure;
  sample: Sample | null;
  track: Track | null;
  selected: string | null;
  onSelect: (link: string | null) => void;
  modelName: string;
}) {
  const [tab, setTab] = useState<Tab>("links");
  const detail = selected ? linkDetail(structure, selected) : null;
  const current = (joint: string) => (sample ? sample.joints[joint] ?? null : null);
  return (
    <div className="flex flex-col">
      <section aria-labelledby="sel-h" className="border-b border-line p-3">
        <h2 id="sel-h" className="mb-2 text-[12px] font-medium text-faint">
          Selection
        </h2>
        {!selected && <p className="text-[12px] text-muted">Select a link in the viewport or in the lists below.</p>}
        {selected && detail && (
          <div className="space-y-2 text-[13px]" data-testid="link-detail">
            <div className="flex items-center gap-2">
              <span className="num font-medium">{selected}</span>
              <Badge tone="neutral">link</Badge>
              <button className="btn ml-auto" onClick={() => onSelect(null)}>
                Clear
              </button>
            </div>
            <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[12px]">
              <dt className="text-muted">Parent joint</dt>
              <dd className="num">
                {detail.parent ? (
                  <>
                    {detail.parent.name} ({detail.parent.type}) from {detail.parent.parent}
                  </>
                ) : (
                  <>none: the root of the model</>
                )}
              </dd>
              {detail.parent && (
                <>
                  <dt className="text-muted">Axis</dt>
                  <dd className="num">{detail.parent.axis ? detail.parent.axis.join(" ") : "fixed"}</dd>
                  <dt className="text-muted">Limits</dt>
                  <dd className="num">
                    {detail.parent.limit
                      ? `${f(detail.parent.limit.lower)} to ${f(detail.parent.limit.upper)} (effort ${f(detail.parent.limit.effort, 1)}, velocity ${f(detail.parent.limit.velocity, 1)})`
                      : detail.parent.type === "continuous"
                        ? "continuous: no position limit"
                        : "none declared"}
                  </dd>
                  <dt className="text-muted">Position now</dt>
                  <dd className="num" data-testid="joint-now">
                    {detail.parent.type === "fixed"
                      ? "fixed"
                      : sample === null
                        ? "no data"
                        : current(detail.parent.name) === null
                          ? "not reported"
                          : `${f(current(detail.parent.name), 4)} rad`}
                    {detail.parent.type !== "fixed" && track?.joints.stats[detail.parent.name] && track.joints.stats[detail.parent.name]!.min === track.joints.stats[detail.parent.name]!.max
                      ? " (constant in this recording)"
                      : ""}
                  </dd>
                </>
              )}
              <dt className="text-muted">Joints below</dt>
              <dd className="num">{detail.children.length ? detail.children.map((j) => j.name).join(", ") : "none"}</dd>
              <dt className="text-muted">Controllers</dt>
              <dd className="num">{detail.drivers.length ? detail.drivers.map((c) => c.name).join(", ") : "none drives its parent joint"}</dd>
              <dt className="text-muted">Sensors on it</dt>
              <dd className="num">{detail.sensors.length ? detail.sensors.map((s) => `${s.name} (${s.type})`).join(", ") : "none"}</dd>
            </dl>
          </div>
        )}
      </section>
      <section aria-labelledby="model-h" className="p-3">
        <h2 id="model-h" className="mb-2 text-[12px] font-medium text-faint">
          Model <span className="num">· {modelName}</span>
        </h2>
        <div role="tablist" aria-label="Model contents" className="mb-2 flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              id={`tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              onClick={() => setTab(t.id)}
              className={clsx("btn", tab === t.id && "bg-sunken")}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="max-h-[320px] overflow-auto text-[12px]" tabIndex={0}>
          {tab === "links" && (
            <ul>
              {structure.links.map((l) => (
                <li key={l.name}>
                  <button className={clsx("num w-full rounded-sm px-1.5 py-1 text-left hover:bg-sunken", selected === l.name && "bg-sunken text-accent")} aria-pressed={selected === l.name} onClick={() => onSelect(l.name)}>
                    {l.name}
                    {l.visuals.some((v) => v.mesh) ? "" : <span className="text-faint"> · no mesh</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {tab === "joints" && (
            <table className="w-full">
              <caption className="sr-only">Joints of the model with their type and the current position</caption>
              <thead>
                <tr className="text-left text-faint">
                  <th scope="col" className="px-1.5 py-1 font-normal">Joint</th>
                  <th scope="col" className="px-1.5 py-1 font-normal">Type</th>
                  <th scope="col" className="px-1.5 py-1 text-right font-normal">Position (rad)</th>
                </tr>
              </thead>
              <tbody>
                {structure.joints.map((j) => (
                  <tr key={j.name} className="border-t border-line">
                    <td className="num px-1.5 py-1">
                      <button className="text-left hover:text-accent" onClick={() => onSelect(j.child)}>
                        {j.name}
                      </button>
                    </td>
                    <td className="px-1.5 py-1 text-muted">{j.type}</td>
                    <td className="num px-1.5 py-1 text-right">{j.type === "fixed" ? "—" : sample ? f(current(j.name), 4) : "no data"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {tab === "controllers" && (
            <ul className="space-y-2">
              {structure.controllers.length === 0 && <li className="text-muted">The model declares no controller.</li>}
              {structure.controllers.map((c, i) => (
                <li key={`${c.name}-${i}`} className="rounded-sm border border-line p-2">
                  <div className="num font-medium">{c.name}</div>
                  <div className="num text-faint">{c.plugin}</div>
                  <div className="mt-1 text-muted">
                    Drives:{" "}
                    {drivenJoints(c).length
                      ? drivenJoints(c).map((j, k) => (
                          <span key={j}>
                            {k > 0 && ", "}
                            <button className="num hover:text-accent" onClick={() => onSelect(structure.joints.find((x) => x.name === j)?.child ?? null)}>
                              {j}
                            </button>
                          </span>
                        ))
                      : "no joint named in its parameters"}
                  </div>
                  <dl className="num mt-1 grid grid-cols-[max-content_1fr] gap-x-2 text-faint">
                    {Object.entries(c.params)
                      .filter(([k]) => !/joint/i.test(k))
                      .slice(0, 8)
                      .map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt>{k}</dt>
                          <dd className="text-ink">{Array.isArray(v) ? v.join(", ") : v}</dd>
                        </div>
                      ))}
                  </dl>
                </li>
              ))}
            </ul>
          )}
          {tab === "sensors" && (
            <table className="w-full">
              <caption className="sr-only">Sensors declared by the model</caption>
              <thead>
                <tr className="text-left text-faint">
                  <th scope="col" className="px-1.5 py-1 font-normal">Sensor</th>
                  <th scope="col" className="px-1.5 py-1 font-normal">Type</th>
                  <th scope="col" className="px-1.5 py-1 font-normal">Topic</th>
                  <th scope="col" className="px-1.5 py-1 text-right font-normal">Hz</th>
                </tr>
              </thead>
              <tbody>
                {structure.sensors.map((s) => (
                  <tr key={s.name} className="border-t border-line">
                    <td className="num px-1.5 py-1">
                      <button className="text-left hover:text-accent" onClick={() => onSelect(s.link)}>
                        {s.name}
                      </button>
                    </td>
                    <td className="px-1.5 py-1 text-muted">{s.type}</td>
                    <td className="num px-1.5 py-1">{s.topic ?? "—"}</td>
                    <td className="num px-1.5 py-1 text-right">{s.update_rate_hz ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
