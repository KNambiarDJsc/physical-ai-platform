"use client";

import clsx from "clsx";
import { ChevronsLeft, ChevronsRight, Pause, Play, StepBack, StepForward } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { nextEvent, type Sample, type Series, type Track, type TwinEvent } from "@/lib/twin";

export const RATES = [0.25, 0.5, 1, 2] as const;
const FRAME_S = 0.05;

const SEVERITY_STROKE: Record<TwinEvent["severity"], string> = {
  info: "stroke-faint",
  warning: "stroke-warn",
  problem: "stroke-bad",
};
const SEVERITY_FILL: Record<TwinEvent["severity"], string> = { info: "bg-faint", warning: "bg-warn", problem: "bg-bad" };

/** Markers closer than a 24 px target would obscure each other: put them in lanes so every one keeps its full hit area. */
function lanes(events: TwinEvent[], duration: number, width: number): number[] {
  const target = 24;
  const ends: number[] = [];
  return events.map((e) => {
    const x = duration > 0 ? (e.t / duration) * width : 0;
    let lane = ends.findIndex((end) => x - end >= target);
    if (lane < 0) lane = ends.length;
    ends[lane] = x;
    return lane;
  });
}

function useWidth() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth || 800));
    ro.observe(el);
    setW(el.clientWidth || 800);
    return () => ro.disconnect();
  }, []);
  return { ref, w };
}

export const sec = (t: number) => `${t.toFixed(2)} s`;

/** One recorded series as an SVG line. The scales only fit the data to the box; no value is computed from it. */
function Chart({
  title,
  unit,
  duration,
  t,
  v,
  step,
  cursor,
  events,
  now,
}: {
  title: string;
  unit: string;
  duration: number;
  t: number[];
  v: number[];
  step: boolean;
  cursor: number;
  events: TwinEvent[];
  now: number | null;
}) {
  const W = 600;
  const H = 46;
  const lo = Math.min(0, ...v);
  const hi = Math.max(0.001, ...v);
  const x = (s: number) => (duration > 0 ? (s / duration) * W : 0);
  const y = (val: number) => H - 3 - ((val - lo) / (hi - lo)) * (H - 8);
  let d = "";
  t.forEach((ti, i) => {
    const vi = v[i] ?? 0;
    if (i === 0) d += `M${x(ti)},${y(vi)}`;
    else d += step ? `H${x(ti)}V${y(vi)}` : `L${x(ti)},${y(vi)}`;
  });
  if (step && t.length) d += `H${W}`;
  return (
    <div className="grid grid-cols-[130px_1fr_88px] items-center gap-2">
      <div className="text-[12px] leading-tight">
        <div className="text-muted">{title}</div>
        <div className="num text-faint">{unit}</div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${title} over ${duration.toFixed(1)} seconds; the current value is in the table to the right`} className="h-[46px] w-full rounded-sm bg-sunken">
        <line x1={0} x2={W} y1={y(0)} y2={y(0)} className="stroke-line" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        {events.map((e) => (
          <line key={e.id} x1={x(e.t)} x2={x(e.t)} y1={0} y2={H} className={SEVERITY_STROKE[e.severity]} strokeWidth={1} strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />
        ))}
        {d && <path d={d} fill="none" className="stroke-accent" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />}
        <line x1={x(cursor)} x2={x(cursor)} y1={0} y2={H} className="stroke-ink" strokeWidth={1} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="num text-right text-[12px]">{now === null ? "no message yet" : now.toFixed(3)}</div>
    </div>
  );
}

export function Timeline({
  track,
  sample,
  t,
  playing,
  rate,
  selectedEvent,
  onSeek,
  onPlay,
  onRate,
  onSelectEvent,
}: {
  track: Track;
  sample: Sample;
  t: number;
  playing: boolean;
  rate: number;
  selectedEvent: string | null;
  onSeek: (t: number) => void;
  onPlay: (p: boolean) => void;
  onRate: (r: number) => void;
  onSelectEvent: (e: TwinEvent) => void;
}) {
  const dur = track.duration_s;
  const { ref: markRef, w: markW } = useWidth();
  const laneOf = lanes(track.events, dur, markW);
  const laneCount = Math.max(1, ...laneOf.map((l) => l + 1));
  const go = (dir: 1 | -1) => {
    const e = nextEvent(track.events, t, dir);
    if (e) onSelectEvent(e);
  };
  const series = (k: string): Series | undefined => track.commands[k];
  const cmd = series("cmd_vel");
  const applied = series("sim_base_cmd_vel");
  return (
    <div className="flex h-full flex-col gap-2 overflow-auto p-3" role="region" aria-label="Timeline and telemetry" tabIndex={0}>
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn" onClick={() => onSeek(0)} aria-label="Go to start" title="Go to start">
          <ChevronsLeft size={14} aria-hidden />
        </button>
        <button className="btn" onClick={() => onSeek(Math.max(0, t - FRAME_S))} aria-label="Step back 0.05 s" title="Step back 0.05 s">
          <StepBack size={14} aria-hidden />
        </button>
        <button className="btn btn-primary" onClick={() => onPlay(!playing)} aria-pressed={playing}>
          {playing ? <Pause size={13} aria-hidden /> : <Play size={13} aria-hidden />} {playing ? "Pause" : "Play"}
        </button>
        <button className="btn" onClick={() => onSeek(Math.min(dur, t + FRAME_S))} aria-label="Step forward 0.05 s" title="Step forward 0.05 s">
          <StepForward size={14} aria-hidden />
        </button>
        <button className="btn" onClick={() => onSeek(dur)} aria-label="Go to end" title="Go to end">
          <ChevronsRight size={14} aria-hidden />
        </button>
        <span className="mx-1 h-4 w-px bg-line" aria-hidden />
        <button className="btn" onClick={() => go(-1)} disabled={!nextEvent(track.events, t, -1)}>
          Previous event
        </button>
        <button className="btn" onClick={() => go(1)} disabled={!nextEvent(track.events, t, 1)}>
          Next event
        </button>
        <label className="ml-auto flex items-center gap-2 text-[12px] text-muted">
          Speed
          <select className="field py-1" value={rate} onChange={(e) => onRate(Number(e.target.value))}>
            {RATES.map((r) => (
              <option key={r} value={r}>
                {r}×
              </option>
            ))}
          </select>
        </label>
        <span className="num text-[13px]" aria-live="off">
          {sec(t)} / {sec(dur)}
        </span>
      </div>
      <div className="relative">
        <input
          type="range"
          className="block w-full accent-[var(--color-accent)]"
          min={0}
          max={dur}
          step={0.01}
          value={t}
          aria-label="Playback position"
          aria-valuetext={`${sec(t)} of ${sec(dur)} on the recording's ${track.clock === "sim" ? "simulation" : "log"} clock`}
          onChange={(e) => onSeek(Number(e.target.value))}
        />
        <div ref={markRef} className="relative mt-1" style={{ height: laneCount * 24 }} aria-label="Events on the timeline" role="group">
          {track.events.map((e, i) => (
            <button
              key={e.id}
              onClick={() => onSelectEvent(e)}
              title={`${sec(e.t)}: ${e.title}`}
              aria-label={`${e.severity}: ${e.title} at ${sec(e.t)}`}
              aria-pressed={selectedEvent === e.id}
              // A 24 px hit area (WCAG 2.5.8) with a slim visible tick; the events are also a list on the left.
              className={clsx("group absolute flex h-6 w-6 -translate-x-1/2 items-center justify-center rounded-sm outline-offset-0 hover:bg-sunken", selectedEvent === e.id && "bg-sunken ring-2 ring-accent")}
              style={{ left: `${dur > 0 ? (e.t / dur) * 100 : 0}%`, top: (laneOf[i] ?? 0) * 24 }}
            >
              <span aria-hidden className={clsx("block h-4 w-1.5 rounded-sm", SEVERITY_FILL[e.severity])} />
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-1.5">
        <Chart title="Base speed (/odom)" unit="m/s" duration={dur} t={track.odom_speed.t} v={track.odom_speed.linear_x} step={false} cursor={t} events={track.events} now={sample.speed} />
        {cmd && <Chart title="Command (/cmd_vel)" unit="m/s, held" duration={dur} t={cmd.t} v={cmd.linear_x} step cursor={t} events={track.events} now={sample.commands["cmd_vel"]?.linear_x ?? null} />}
        {applied && <Chart title="Applied (/sim/base_cmd_vel)" unit="m/s, held" duration={dur} t={applied.t} v={applied.linear_x} step cursor={t} events={track.events} now={sample.commands["sim_base_cmd_vel"]?.linear_x ?? null} />}
      </div>
    </div>
  );
}
