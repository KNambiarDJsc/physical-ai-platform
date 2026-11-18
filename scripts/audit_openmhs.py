"""CORE-001: audit the pinned OpenMHS engine by running it, not by reading claims about it.

Runs the binary named by OPENMHS_BIN against the fixtures and the RFC 0004 corpus of the pinned source tree
(exported by scripts/build-openmhs.sh into .engine/src-<commit>), checks the results the platform relies on,
and writes harness/evaluation-results/openmhs-audit.json. Exit 0 when every check passes.

Usage: OPENMHS_BIN=... python scripts/audit_openmhs.py [--src .engine/src-<commit>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def run(binary: str, *args: str) -> tuple[int, str, str]:
    p = subprocess.run([binary, *args], capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    lock = json.loads((ROOT / "engine.lock.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / ".engine" / f"src-{lock['commit']}"))
    ns = ap.parse_args()
    src = Path(ns.src)
    binary = os.environ.get("OPENMHS_BIN")
    build = ROOT / ".engine" / "build.json"
    expected = None
    if not binary and build.exists():
        info = json.loads(build.read_text(encoding="utf-8"))
        if info.get("commit") == lock["commit"]:
            binary, expected = info["binary"], info["sha256"]
    if not binary:
        print("set OPENMHS_BIN or build the pinned engine with scripts/build-openmhs.sh", file=sys.stderr)
        return 2
    binary = str(Path(binary).resolve())
    fixtures = src / "crates" / "openmhs-ops" / "tests" / "fixtures"
    corpus = src / "research" / "outcome-verifier" / "corpus" / "cases"
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: Any) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail if not isinstance(detail, dict) else json.dumps(detail)}")

    digest = "sha256:" + hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    code, version, _ = run(binary, "--version")
    check("binary runs", code == 0, {"version": version.strip(), "sha256": digest})
    if expected is not None:
        check("binary is the pinned build (.engine/build.json)", digest == expected, {"expected": expected})

    # 1. The 469-record fixture with 124 verdicts.
    recs = [
        json.loads(line)
        for line in (fixtures / "coresense_real_flights_verified.jsonl").open(encoding="utf-8")
        if line.strip()
    ]
    kinds = Counter(r.get("type") for r in recs)
    check(
        "coresense fixture: 469 records, 124 outcome.verified",
        len(recs) == 469 and kinds["outcome.verified"] == 124,
        {"records": len(recs), "outcome.verified": kinds["outcome.verified"]},
    )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        # 2. Ingest + verified release comparison on the Gazebo A/B fixture.
        store = str(t / "gazebo.sqlite")
        code, out, err = run(binary, "--json", "ops", "ingest", "--store", store, str(fixtures / "gazebo_ab.jsonl"))
        ing = json.loads(out) if code == 0 else {"error": err}
        check(
            "ops ingest gazebo_ab: no rejections",
            code == 0 and ing.get("rejected") == [],
            {"ingested": ing.get("ingested"), "rules": ing.get("rebuild", {}).get("rules_version")},
        )
        code, out, err = run(
            binary,
            "--json",
            "ops",
            "compare",
            "--store",
            store,
            "--task-type",
            "lift",
            "--a",
            "engine-bullet",
            "--b",
            "tol-0.01",
            "--verified",
        )
        c = json.loads(out) if code == 0 else {}
        ok = (
            code == 0
            and c["a"]["attempt_outcomes"] == [15, 15, 0]
            and c["b"]["attempt_outcomes"] == [30, 0, 0]
            and abs(c["difference"][0] + 0.5) < 1e-12
            and c["difference_method"] == "newcombe"
            and c["verdict"] == "insufficient_evidence"
        )
        check(
            "ops compare --verified gazebo: 15/30 -> 0/30 failed, newcombe -0.5, insufficient_evidence",
            ok,
            {
                "a": c.get("a", {}).get("attempt_outcomes"),
                "b": c.get("b", {}).get("attempt_outcomes"),
                "difference": c.get("difference"),
                "ci95_a": c.get("a", {}).get("ci95"),
                "verdict": c.get("verdict"),
                "reasons": c.get("reasons"),
            },
        )
        # 3. Reported comparison on the same data: the robot reported no failures in either arm.
        code, out, _ = run(
            binary,
            "--json",
            "ops",
            "compare",
            "--store",
            store,
            "--task-type",
            "lift",
            "--a",
            "engine-bullet",
            "--b",
            "tol-0.01",
        )
        r = json.loads(out) if code == 0 else {}
        check(
            "ops compare reported gazebo: 0 reported failures in both arms",
            code == 0 and r["a"]["failed"] == 0 and r["b"]["failed"] == 0,
            {"a": r.get("a", {}).get("attempt_outcomes"), "b": r.get("b", {}).get("attempt_outcomes")},
        )

        # 4. Real flights: verified events ingest, incidents exist.
        store2 = str(t / "coresense.sqlite")
        code, out, err = run(
            binary,
            "--json",
            "ops",
            "ingest",
            "--store",
            store2,
            str(fixtures / "coresense_real_flights_verified.jsonl"),
        )
        ing2 = json.loads(out) if code == 0 else {"error": err}
        check(
            "ops ingest coresense verified: no rejections",
            code == 0 and ing2.get("rejected") == [],
            {"ingested": ing2.get("ingested"), "incidents": ing2.get("rebuild", {}).get("incidents")},
        )
        code, out, _ = run(binary, "--json", "ops", "incidents", "--store", store2)
        inc = json.loads(out) if code == 0 else []
        check("ops incidents --json lists incidents", code == 0 and len(inc) > 0, {"incidents": len(inc)})
        if inc:
            code, out, _ = run(binary, "--json", "ops", "show", "--store", store2, inc[0]["incident_id"])
            show = json.loads(out) if code == 0 else {}
            check(
                "ops show --json returns a timeline",
                code == 0 and len(show.get("members", [])) > 0,
                {"members": len(show.get("members", [])), "shape": bool(show.get("shape"))},
            )

        # 5. Paired comparison (simulation policy rollouts).
        store3 = str(t / "policy.sqlite")
        run(binary, "--json", "ops", "ingest", "--store", store3, str(fixtures / "policy_pusht_rollouts.jsonl"))
        code, out, _ = run(
            binary,
            "--json",
            "ops",
            "compare",
            "--store",
            store3,
            "--task-type",
            "pusht",
            "--a",
            "ddpm-100",
            "--b",
            "ddim-10",
            "--paired",
        )
        p = json.loads(out) if code == 0 else {}
        paired = p.get("paired") or {}
        check(
            "ops compare --paired: McNemar exact and paired interval present",
            code == 0 and paired.get("pairs") == 20 and paired.get("mcnemar_p") is not None,
            {
                "pairs": paired.get("pairs"),
                "mcnemar_p": paired.get("mcnemar_p"),
                "difference": paired.get("difference"),
                "verdict": p.get("verdict"),
            },
        )

    # 6. RFC 0004 corpus: every case's verdict equals its expected verdict.
    results = {}
    for case in sorted(corpus.glob("*/*")):
        expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))["verdict"]
        code, out, err = run(
            binary,
            "--json",
            "outcome",
            "verify",
            "--contract",
            str(case / "contract.json"),
            "--evidence",
            str(case / "evidence.jsonl"),
        )
        got = json.loads(out)["verdict"] if out.strip() else f"error {code}: {err.strip()[:200]}"
        exit_ok = {"SATISFIED": 0, "VIOLATED": 3, "UNKNOWN": 4}.get(got) == code
        results[f"{case.parent.name}/{case.name}"] = {"expected": expected, "got": got, "exit_ok": exit_ok}
    mismatched = {k: v for k, v in results.items() if v["expected"] != v["got"] or not v["exit_ok"]}
    check(
        "outcome verify corpus: all cases match expected verdict and exit code",
        len(results) > 0 and not mismatched,
        {
            "cases": len(results),
            "mismatched": mismatched,
            "verdicts": dict(Counter(v["got"] for v in results.values())),
        },
    )

    out_path = ROOT / "harness" / "evaluation-results" / "openmhs-audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "engine": {"commit": lock["commit"], "binary_sha256": digest, "version": version.strip()},
        "source_tree": src.name,
        "checks": checks,
        "corpus": results,
    }
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    failed = [c["check"] for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed; written {out_path.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
