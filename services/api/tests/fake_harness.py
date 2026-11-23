"""A stand-in for ``pap-harness ask`` used by the API tests: same command line, same trace file, no model.

It labels itself ("fake") in the trace. It exists so the API's session handling (who may ask, limits, isolation,
secrets, the `--` before the question, the caller's credential) is tested without a model or the harness environment.
How the real harness behaves is tested in packages/agent-harness, and with a real model only by a real run."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(prog="pap-harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("question")
    for opt in ("--org", "--api", "--max-usd", "--max-steps", "--timeout-s", "--state", "--session"):
        a.add_argument(opt)
    a.add_argument("--allow-no-model", action="store_true")
    a.add_argument("--allow-requests", action="store_true")
    a.add_argument("--draft-requests", action="store_true")
    ns = ap.parse_args()
    state = Path(ns.state)
    (state / "traces").mkdir(parents=True, exist_ok=True)
    seen = {
        "argv": sys.argv[1:],
        "token": os.environ.get("PAP_API_TOKEN"),
        "pap_env": sorted(k for k in os.environ if k.startswith("PAP_")),
        "org": ns.org,
    }
    (state / f"seen-{ns.session}.json").write_text(json.dumps(seen), encoding="utf-8")

    q = ns.question
    if q.startswith("FAIL"):
        print(
            f"boom: key={os.environ.get('PAP_LLM_API_KEY', '')} token={os.environ.get('PAP_API_TOKEN', '')}",
            file=sys.stderr,
        )
        sys.exit(3)
    if q.startswith("SLOW"):
        time.sleep(1.5)
    usd = float(os.environ.get("FAKE_USD", "0.0123"))
    trace = {
        "schema": "pap.agent-trace/1", "id": ns.session, "org": ns.org, "model": "fake", "question": q,
        "allow_requests": ns.allow_requests, "answer": f"fake answer to: {q}", "stop": "answered", "route": "agent",
        "steps": [
            {"n": 1, "kind": "tool", "tool": "list_experiments", "input": {"org": ns.org}, "permitted": True,
             "output_sha256": "sha256:" + "a" * 64, "output": {"experiments": []}, "error": None, "t": 0.1},
            {"n": 2, "kind": "tool", "tool": "get_run", "input": {"org": ns.org}, "permitted": True,
             "output_sha256": "sha256:" + "b" * 64, "output": {"blob": "x" * 30_000}, "error": None, "t": 0.2},
            {"n": 3, "kind": "model", "input_tokens": 10, "output_tokens": 5, "t": 0.3},
        ],
        "grounding": {"unsupported": [], "uncited": []},
        "usage": {"model_calls": 1, "input_tokens": 10, "output_tokens": 5, "usd": usd, "max_usd": 0.25,
                  "max_tokens": 200000, "priced": True},
        "duration_s": 0.3,
    }  # fmt: skip
    if ns.draft_requests and q.startswith("DRAFT"):
        trace["steps"].append(
            {
                "n": 4,
                "kind": "tool",
                "tool": "propose_experiment",
                "permitted": True,
                "error": None,
                "t": 0.4,
                "input": {
                    "org": ns.org,
                    "workflow": "dispense",
                    "rationale": "Repeat once.",
                    "evidence_ids": ["run:x"],
                },
                "output_sha256": "sha256:" + "c" * 64,
                "output": {"drafted": True, "filed": False, "request": {"workflow": "dispense"}},
            }
        )
    (state / "traces" / f"{ns.session}.json").write_text(json.dumps(trace), encoding="utf-8")


if __name__ == "__main__":
    main()
