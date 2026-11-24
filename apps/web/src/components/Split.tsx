"use client";

import clsx from "clsx";
import { useCallback, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

/**
 * A resizable pane next to flexible content (the WAI-ARIA window splitter pattern). Drag the separator, or focus it and
 * use the arrow keys (Shift for bigger steps), Home and End. Sizes live in component state only.
 */
export function Split({
  side,
  label,
  initial,
  min,
  max,
  pane,
  children,
  className,
}: {
  side: "start" | "end" | "bottom";
  label: string;
  initial: number;
  min: number;
  max: number;
  pane: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [size, setSize] = useState(initial);
  const drag = useRef<{ start: number; size: number } | null>(null);
  const vertical = side === "bottom";
  const clamp = useCallback((v: number) => Math.round(Math.min(max, Math.max(min, v))), [min, max]);
  const sign = side === "start" ? 1 : -1;

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { start: vertical ? e.clientY : e.clientX, size };
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const delta = (vertical ? e.clientY : e.clientX) - drag.current.start;
    setSize(clamp(drag.current.size + delta * sign));
  };
  const end = () => {
    drag.current = null;
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 64 : 16;
    const grow = vertical ? "ArrowUp" : side === "start" ? "ArrowRight" : "ArrowLeft";
    const shrink = vertical ? "ArrowDown" : side === "start" ? "ArrowLeft" : "ArrowRight";
    if (e.key === grow) setSize((s) => clamp(s + step));
    else if (e.key === shrink) setSize((s) => clamp(s - step));
    else if (e.key === "Home") setSize(min);
    else if (e.key === "End") setSize(max);
    else return;
    e.preventDefault();
  };

  const separator = (
    <div
      role="separator"
      tabIndex={0}
      aria-label={label}
      aria-orientation={vertical ? "horizontal" : "vertical"}
      aria-valuenow={size}
      aria-valuemin={min}
      aria-valuemax={max}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
      onLostPointerCapture={end}
      onKeyDown={onKeyDown}
      className={clsx(
        "group relative shrink-0 touch-none bg-line transition-colors duration-150 hover:bg-accent focus-visible:bg-accent",
        vertical ? "h-px cursor-row-resize" : "w-px cursor-col-resize",
      )}
    >
      {/* a wider invisible hit area than the 1 px line */}
      <span aria-hidden className={clsx("absolute", vertical ? "inset-x-0 -inset-y-1.5" : "inset-y-0 -inset-x-1.5")} />
      <span aria-hidden className={clsx("split-grip", vertical ? "split-grip-horizontal" : "split-grip-vertical")} />
    </div>
  );
  const sized = <div style={vertical ? { height: size } : { width: size }} className="split-pane min-h-0 min-w-0 shrink-0 overflow-auto">{pane}</div>;
  const rest = <div className="split-content min-h-0 min-w-0 flex-1 overflow-auto">{children}</div>;
  return (
    <div className={clsx("workspace-split flex min-h-0 min-w-0", vertical ? "flex-col" : "flex-row", className)}>
      {side === "start" ? (
        <>
          {sized}
          {separator}
          {rest}
        </>
      ) : (
        <>
          {rest}
          {separator}
          {sized}
        </>
      )}
    </div>
  );
}
