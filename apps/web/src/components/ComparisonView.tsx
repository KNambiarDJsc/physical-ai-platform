import Link from "next/link";
import type { Arm, Comparison, ComparisonOut } from "@/lib/api/client";
import { CLASS_LABEL, interval, pct, points, shortDigest } from "@/lib/format";
import { Notice, Panel } from "./AppShell";
import { ClassBadge, EvidenceClassBadge, IntervalPlot, Table, Td, VerdictBadge } from "./ui";

/** Renders an evaluation's stored engine outputs. Every number shown is a field of the API response. */
export function ComparisonView({ data, episodesHref }: { data: ComparisonOut; episodesHref: string }) {
  const prov = (data.provenance ?? {}) as Record<string, unknown>;
  const engine = (prov.engine ?? {}) as Record<string, string>;
  const classes = (data.summary?.classes ?? {}) as Record<string, Record<string, number>>;
  const labels = [data.reported.result.a.selector, data.reported.result.b.selector];
  const classNames = Object.keys(CLASS_LABEL).filter((c) => labels.some((l) => classes[l]?.[c]));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <EvidenceClassBadge classes={prov.evidence_class as string[] | undefined} />
        <span className="text-xs text-muted">task type</span>
        <span className="num text-xs">{data.reported.result.task_type}</span>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ComparisonPanel title="Reported by the robot" c={data.reported.result} />
        {data.verified ? (
          <ComparisonPanel title="Independently verified" c={data.verified.result} />
        ) : (
          <Panel title="Independently verified">
            <Notice tone="info">The mapping declares no independent evidence, so there is no verified comparison.</Notice>
          </Panel>
        )}
      </div>

      <Panel title="Outcome per episode (reported value × verifier verdict)">
        <Table head={["Class", ...labels.map((l) => l)]} caption="Episode outcome classes per release">
          {classNames.map((c) => (
            <tr key={c}>
              <Td>
                <Link className="hover:underline" href={`${episodesHref}?outcome_class=${c}`}>
                  <ClassBadge value={c} />
                </Link>
              </Td>
              {labels.map((l) => (
                <Td key={l} num>
                  {classes[l]?.[c] ?? 0}
                </Td>
              ))}
            </tr>
          ))}
        </Table>
        <p className="mt-2 text-xs text-faint">
          Counts of episodes, not rates. A contradiction is a reported success the evidence refutes (or the reverse);
          unknown means evidence was present but the verifier could not decide.{" "}
          <Link className="text-accent underline" href={episodesHref}>
            Inspect episodes
          </Link>
        </p>
      </Panel>

      {data.paired && <PairedPanel c={data.paired.result} />}

      <Panel title="Provenance">
        <dl className="grid gap-x-6 gap-y-1 text-[13px] break-all sm:grid-cols-[max-content_1fr]">
          <dt className="text-muted">Engine</dt>
          <dd className="num">
            {engine.version} · commit {String(engine.commit ?? "").slice(0, 10)} · binary {shortDigest(engine.binary_sha256)}
          </dd>
          <dt className="text-muted">Correlation rules</dt>
          <dd className="num">{String(prov.rules_version ?? "—")}</dd>
          <dt className="text-muted">Mapping</dt>
          <dd className="num">{String(prov.mapping ?? "—")}</dd>
          <dt className="text-muted">Inputs</dt>
          <dd className="num">
            {Object.entries((prov.inputs ?? {}) as Record<string, string[]>).map(([rel, shas]) => (
              <div key={rel}>
                {rel}: {shas.map(shortDigest).join(", ")}
              </div>
            ))}
          </dd>
          <dt className="text-muted">Evidence bundle</dt>
          <dd className="num">
            events {shortDigest((prov.bundle as Record<string, string> | undefined)?.events)} · engine store{" "}
            {shortDigest((prov.bundle as Record<string, string> | undefined)?.engine_store)}
          </dd>
          <dt className="text-muted">Input checksum</dt>
          <dd className="num">{shortDigest(String(prov.input_sha256 ?? ""))}</dd>
          <dt className="text-muted">Output digests</dt>
          <dd className="num">
            reported {shortDigest(data.reported.raw_sha256)}
            {data.verified && <> · verified {shortDigest(data.verified.raw_sha256)}</>}
          </dd>
        </dl>
      </Panel>
    </div>
  );
}

function outcomes(o: readonly number[]): string {
  return `${o[0] ?? 0} ok, ${o[1] ?? 0} failed, ${o[2] ?? 0} unknown`;
}

function ArmRow({ name, arm }: { name: string; arm: Arm }) {
  return (
    <tr>
      <Td>
        <span className="text-muted">{name}</span> <span className="num">{arm.selector}</span>
      </Td>
      <Td num>{arm.succeeded + arm.failed}</Td>
      <Td num>{arm.failed}</Td>
      <Td num>{arm.unknown}</Td>
      <Td num>{pct(arm.rate)}</Td>
      <Td num>{interval(arm.ci95)}</Td>
      <Td num>{arm.unknown_bounds ? `${pct(arm.unknown_bounds[0])} / ${pct(arm.unknown_bounds[1])}` : "—"}</Td>
    </tr>
  );
}

export function ComparisonPanel({ title, c }: { title: string; c: Comparison }) {
  return (
    <Panel title={title}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <VerdictBadge verdict={c.verdict} />
        <span className="text-[13px] text-muted">{c.reasons.join("; ")}</span>
      </div>
      <Table
        head={["Release", `Known (${c.a.unit}s)`, "Failed", "Unknown", "Failure rate", "95% interval", "Unknowns as ok / failed"]}
        caption={`${title}: failure rate per release`}
      >
        <ArmRow name="baseline" arm={c.a} />
        <ArmRow name="candidate" arm={c.b} />
      </Table>
      <div className="mt-3 grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
        <IntervalPlot
          rows={[
            { label: "baseline", rate: c.a.rate, ci: c.a.ci95 },
            { label: "candidate", rate: c.b.rate, ci: c.b.ci95 },
          ]}
        />
        <div className="text-[13px]">
          <div className="text-xs text-muted">Difference (candidate − baseline)</div>
          <div className="num text-base">{points(c.difference?.[0])}</div>
          <div className="num text-xs text-muted">
            95% {c.difference ? `${points(c.difference[1])} to ${points(c.difference[2])}` : "—"} · {c.difference_method}
          </div>
          {c.unknown_bounds && (
            <div className="num text-xs text-muted">
              unknowns counted both ways: {points(c.unknown_bounds[0])} to {points(c.unknown_bounds[1])}
            </div>
          )}
        </div>
      </div>
      <p className="mt-2 text-xs text-faint">
        Attempts: baseline {c.a.attempts} ({outcomes(c.a.attempt_outcomes)}), candidate {c.b.attempts} (
        {outcomes(c.b.attempt_outcomes)}). Rates are descriptive; only the verdict above is an inferential claim, under
        the engine&apos;s rules {c.rules_version}.
      </p>
      {c.warnings.length > 0 && (
        <div className="mt-3 space-y-1">
          {c.warnings.map((w) => (
            <Notice key={w} tone="warn">
              {w}
            </Notice>
          ))}
        </div>
      )}
      {c.strata.length > 1 && (
        <div className="mt-3">
          <Table head={["Site", "Baseline failed / known", "Candidate failed / known", "Difference"]} caption="Per site">
            {c.strata.map((s) => (
              <tr key={s.site}>
                <Td>{s.site}</Td>
                <Td num>{`${s.a[0]} / ${s.a[1]}`}</Td>
                <Td num>{`${s.b[0]} / ${s.b[1]}`}</Td>
                <Td num>{points(s.difference?.[0])}</Td>
              </tr>
            ))}
          </Table>
        </div>
      )}
    </Panel>
  );
}

function PairedPanel({ c }: { c: Comparison }) {
  const p = c.paired;
  if (!p) return null;
  return (
    <Panel title={`Paired by scenario (${c.outcome})`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <VerdictBadge verdict={c.verdict} />
        <span className="text-[13px] text-muted">{c.reasons.join("; ")}</span>
      </div>
      <Table head={["Pairs", "Both fail", "Only baseline fails", "Only candidate fails", "Neither", "Unknown pairs", "McNemar p", "Paired difference (95%)"]}>
        <tr>
          <Td num>{p.pairs}</Td>
          <Td num>{p.both_fail}</Td>
          <Td num>{p.a_only_fails}</Td>
          <Td num>{p.b_only_fails}</Td>
          <Td num>{p.both_ok}</Td>
          <Td num>{p.unknown_pairs}</Td>
          <Td num>{p.mcnemar_p === null || p.mcnemar_p === undefined ? "—" : p.mcnemar_p.toFixed(3)}</Td>
          <Td num>{p.difference ? `${points(p.difference[0])} (${points(p.difference[1])} to ${points(p.difference[2])})` : "—"}</Td>
        </tr>
      </Table>
    </Panel>
  );
}
