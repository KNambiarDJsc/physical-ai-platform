/**
 * Presentation only. These functions format numbers the engine computed; they never compute a statistic.
 */

export function pct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "—";
  return `${(x * 100).toFixed(digits)}%`;
}

export function interval(ci: readonly [number, number] | null | undefined, digits = 1): string {
  if (!ci) return "—";
  return `${pct(ci[0], digits)} – ${pct(ci[1], digits)}`;
}

/** A difference in failure rate as signed percentage points. */
export function points(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "—";
  const v = x * 100;
  const s = v.toFixed(digits);
  return `${v > 0 ? "+" : v < 0 ? "" : "±"}${s} pts`;
}

export const VERDICT_LABEL: Record<string, string> = {
  regression: "Regression",
  improvement: "Improvement",
  no_change: "No change",
  insufficient_evidence: "Insufficient evidence",
};

export const CLASS_LABEL: Record<string, string> = {
  supported_success: "Supported success",
  verified_success: "Verified success",
  verified_failure: "Verified failure",
  contradiction: "Contradiction",
  unknown: "Unknown",
  reported_only: "Reported only",
  insufficient_evidence: "Insufficient evidence",
};

/**
 * One timestamp format everywhere (DESIGN.md §9): local time as YYYY-MM-DD HH:mm, unambiguous in every locale.
 * The full ISO instant goes in the title and the dateTime attribute.
 */
export function timestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function shortDigest(d: string | null | undefined): string {
  if (!d) return "—";
  return d.replace(/^sha256:/, "").slice(0, 12);
}
