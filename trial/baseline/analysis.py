"""Conventional baseline: the trial exercise done with a plain Python script, no platform.

    python trial/baseline/analysis.py mujoco A D          # baseline vs candidate group
    python trial/baseline/analysis.py coresense no_failure panel_failure

Standard library only (Python 3.10+). Reads the same raw CSVs the platform ingests and applies the same
definitions the exercise asks about, so the answers can be compared:

- reported failure: the robot's own status is not "succeeded" (MuJoCo) / not "SUCCEEDED" (CoreSense); a CANCELED
  goal claims nothing and is left out of the reported outcomes;
- verified failure: the independent measurement violates the rule (MuJoCo: fingertip error > 0.02 m at the report;
  CoreSense: |dx| or |dy| > 0.20 m at the claim); no measurement = unknown;
- one scenario per initial condition (MuJoCo) or waypoint (CoreSense), judged by the majority of its attempts;
- 95 % Wilson interval per rate, Newcombe hybrid-score interval for the difference (candidate minus baseline),
  exact McNemar test for paired scenarios;
- verdict: insufficient_evidence with fewer than 30 known scenarios in an arm or fewer than 5 failures in both
  arms together; otherwise regression / improvement if the whole interval is above +0.01 / below -0.01,
  no_change if it lies within +-0.01, else insufficient_evidence.

These are written to match the platform's engine (OpenMHS, rules corr-1) so the two can be compared;
tests/test_trial_baseline.py checks that they agree on the shipped data. Things this script does NOT do, which the
platform does: the paired confidence interval, provenance (engine build, mapping and input checksums), a stored
and reproducible report, the per-episode verifier record, and access control.
"""

from __future__ import annotations

import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Z = 1.959963984540054  # two-sided 95 %
MIN_KNOWN, MIN_FAILURES, MARGIN = 30, 5, 0.01


def mujoco(group: str) -> list[dict]:
    rows = csv.DictReader((ROOT / "examples/mujoco-regression/data" / f"{group}.csv").open(encoding="utf-8"))
    out = []
    for r in rows:
        err = float(r["tip_error_m"])
        failed = r["robot_status"] != "succeeded"
        out.append({"scenario": r["scenario"], "episode": r["episode_id"], "reported_fail": failed,
                    "verified_fail": err > 0.02, "value": err})  # fmt: skip
    return out


def coresense(condition: str) -> list[dict]:
    rows = csv.DictReader((ROOT / "examples/coresense/data" / f"{condition}.csv").open(encoding="utf-8"))
    out = []
    for r in rows:
        known = r["dx_m"] != "" and r["dy_m"] != ""
        off = known and (abs(float(r["dx_m"])) > 0.20 or abs(float(r["dy_m"])) > 0.20)
        # A cancelled goal (re-assigned by the swarm) claims nothing either way: neither a reported success nor a
        # reported failure. Counting it as a failure is an easy mistake; the platform's first version made it too.
        claim = None if r["robot_status"] == "CANCELED" else r["robot_status"] != "SUCCEEDED"
        out.append({"scenario": r["waypoint"], "episode": r["episode_id"], "reported_fail": claim,
                    "verified_fail": off if known else None, "value": None})  # fmt: skip
    return out


def by_scenario(rows: list[dict], key: str) -> dict[str, bool | None]:
    """Majority of the scenario's known attempts; a tie or no known attempt is unknown."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r[key] is not None:
            votes[r["scenario"]][r[key]] += 1
        else:
            votes[r["scenario"]]
    out: dict[str, bool | None] = {}
    for s, c in votes.items():
        out[s] = None if c[True] == c[False] else c[True] > c[False]
    return out


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def newcombe(ka: int, na: int, kb: int, nb: int) -> tuple[float, float, float]:
    pa, pb = ka / na, kb / nb
    la, ua = wilson(ka, na)
    lb, ub = wilson(kb, nb)
    d = pb - pa
    return d, d - math.sqrt((pb - lb) ** 2 + (ua - pa) ** 2), d + math.sqrt((ub - pb) ** 2 + (pa - la) ** 2)


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def compare(a: dict[str, bool | None], b: dict[str, bool | None]) -> dict:
    ka, na = sum(v is True for v in a.values()), sum(v is not None for v in a.values())
    kb, nb = sum(v is True for v in b.values()), sum(v is not None for v in b.values())
    out = {"a": (ka, na), "b": (kb, nb), "rate_a": ka / na if na else None, "rate_b": kb / nb if nb else None}
    if na < MIN_KNOWN or nb < MIN_KNOWN:
        return {**out, "verdict": "insufficient_evidence", "reason": "fewer than 30 known scenarios in an arm"}
    if ka + kb < MIN_FAILURES:
        return {**out, "verdict": "insufficient_evidence", "reason": "fewer than 5 failures in both arms together"}
    d, lo, hi = newcombe(ka, na, kb, nb)
    verdict = ("regression" if lo > MARGIN else "improvement" if hi < -MARGIN
               else "no_change" if lo >= -MARGIN and hi <= MARGIN else "insufficient_evidence")  # fmt: skip
    shared = [s for s in a if s in b and a[s] is not None and b[s] is not None]
    only_b = sum(b[s] and not a[s] for s in shared)
    only_a = sum(a[s] and not b[s] for s in shared)
    return {**out, "difference": (d, lo, hi), "verdict": verdict, "pairs": len(shared),
            "a_only_fails": only_a, "b_only_fails": only_b, "mcnemar_p": mcnemar_exact(only_a, only_b)}  # fmt: skip


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in ("mujoco", "coresense"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    load = mujoco if sys.argv[1] == "mujoco" else coresense
    a_rows, b_rows = load(sys.argv[2]), load(sys.argv[3])
    for key, title in (("reported_fail", "Reported by the robot"), ("verified_fail", "Independently verified")):
        r = compare(by_scenario(a_rows, key), by_scenario(b_rows, key))
        print(f"{title}: {r['verdict']}" + (f"  ({r['reason']})" if "reason" in r else ""))
        for arm, label in (("a", sys.argv[2]), ("b", sys.argv[3])):
            k, n = r[arm]
            lo, hi = wilson(k, n)
            print(
                f"  {label}: {k}/{n} scenarios failed = {k / n:.3f}  95% CI [{lo:.3f}, {hi:.3f}]"
                if n
                else f"  {label}: no known scenario"
            )
        if "difference" in r:
            d, lo, hi = r["difference"]
            print(f"  difference {d:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]  paired: {r['pairs']} pairs, "
                  f"{r['b_only_fails']} only candidate failed, {r['a_only_fails']} only baseline failed, "
                  f"McNemar p {r['mcnemar_p']:.3g}")  # fmt: skip
    disagree = [
        r
        for r in b_rows
        if None not in (r["verified_fail"], r["reported_fail"]) and r["reported_fail"] != r["verified_fail"]
    ]
    print(f"Candidate episodes where report and measurement disagree: {len(disagree)} of {len(b_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
