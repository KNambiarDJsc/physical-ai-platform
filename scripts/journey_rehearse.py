# ruff: noqa: E501 - narrative output and one-line records read better unwrapped
"""Rehearse the whole Laboratory experiment journey against a running stack, through the API, and keep the real evidence.

For a fresh workspace it: seeds the procedures (journey_seed.py), has the researcher (ada) request each procedure, has a
different engineer (bob) approve it, waits for the worker and the engine, exports each run's evidence report, and, if the
server has a model configured, asks the agent to investigate the failed run (drafting a follow-up) and to approve it
(which it must not be able to do). It writes docs/demo/evidence/ and a rehearsal record. Nothing is simulated by this
script: every number comes from the stack. It stores no key; spend is the server's own capped per-session limit.

    uv run python scripts/journey_rehearse.py --org lab-journey-r1 [--no-agent] [--out docs/demo/evidence]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROC = {"success": "dispense-50ul", "failing": "dispense-50ul-blocked-line"}


def is_draft(st: dict[str, Any]) -> bool:
    """A step the agent only DRAFTED (a tool output may be a list or a dict)."""
    out = st.get("output")
    return isinstance(out, dict) and bool(out.get("drafted"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--org", default="lab-journey-r1")
    ap.add_argument("--out", default=str(ROOT / "docs" / "demo" / "evidence"))
    ap.add_argument("--no-agent", action="store_true", help="skip the model sessions (no spend)")
    ns = ap.parse_args()
    out = Path(ns.out)
    out.mkdir(parents=True, exist_ok=True)
    o = f"/api/v1/orgs/{ns.org}"
    ada = httpx.Client(base_url=ns.api, headers={"Authorization": "Bearer dev:ada"}, timeout=120)
    bob = httpx.Client(base_url=ns.api, headers={"Authorization": "Bearer dev:bob"}, timeout=120)
    record: dict[str, Any] = {"org": ns.org, "steps": []}

    def step(name: str, ok: bool, detail: Any = None) -> None:
        record["steps"].append({"step": name, "ok": ok, "detail": detail})
        print(("PASS  " if ok else "FAIL  ") + name + (f": {detail}" if detail and not ok else ""))
        if not ok:
            (out / "rehearsal.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
            sys.exit(1)

    seed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "journey_seed.py"), "--api", ns.api, "--org", ns.org],
        capture_output=True, text=True, cwd=ROOT,
    )  # fmt: skip
    step("workspace seeded: devices discovered and two procedures created", seed.returncode == 0, seed.stderr[-300:])

    runs: dict[str, str] = {}
    for kind, slug in PROC.items():
        p = ada.post(
            f"{o}/experiment-proposals",
            json={"workflow": slug, "rationale": f"Rehearsal: the {kind} case, requested by ada."},
        )
        step(f"ada requests {slug}", p.status_code == 201, p.text[:200])
        pid = p.json()["id"]
        own = ada.post(f"{o}/experiment-proposals/{pid}/approve")
        step(
            f"ada cannot approve her own request for {slug}",
            own.status_code == 403 and "separation_of_duties" in own.text,
            own.text[:200],
        )
        ap_ = bob.post(f"{o}/experiment-proposals/{pid}/approve")
        step(f"bob approves {slug}", ap_.status_code == 200 and bool(ap_.json().get("run_id")), ap_.text[:200])
        rid = ap_.json()["run_id"]
        runs[kind] = rid
        for _ in range(240):
            d = ada.get(f"{o}/workflow-runs/{rid}").json()
            if d["state"] not in ("queued", "running"):
                break
            time.sleep(1)
        step(f"the worker executed {slug}", d["state"] == "succeeded", d["state"])
        record[kind] = {
            "run": rid, "verdict": d["verdict"], "outcome_class": d["outcome_class"],
            "reported": d["reported"], "steps": [f"{s['device']}.{s['action']}" for s in d["steps"]],
            "measured": (d["verification"]["evidence"][1]["value"] if d.get("verification") else None),
            "engine": (d["provenance"] or {}).get("engine"),
        }  # fmt: skip
    step("the healthy run is SATISFIED by the engine", record["success"]["verdict"] == "SATISFIED", record["success"])
    step(
        "the faulty run is a contradiction: the pump reported success, the engine says VIOLATED",
        record["failing"]["verdict"] == "VIOLATED"
        and record["failing"]["outcome_class"] == "contradiction"
        and record["failing"]["reported"]["value"] == "succeeded",
        record["failing"],
    )

    for kind, rid in runs.items():
        for ext in ("json", "html"):
            r = ada.get(f"{o}/workflow-runs/{rid}/report.{ext}")
            again = ada.get(f"{o}/workflow-runs/{rid}/report.{ext}")
            ok = r.status_code == 200 and r.content == again.content
            step(f"{kind} run report.{ext} exported and byte-identical on repeat", ok, r.status_code)
            (out / f"{kind}-run.report.{ext}").write_bytes(r.content)
    for slug in PROC.values():
        w = ada.get(f"{o}/workflows").json()
        (out / f"{slug}.workflow.json").write_text(
            json.dumps(next(x for x in w if x["slug"] == slug), indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    status = ada.get(f"{o}/agent/status").json()
    record["agent_status"] = {
        k: status[k] for k in ("runner_available", "model_configured", "model", "priced", "session_usd_cap")
    }
    if ns.no_agent or not status["model_configured"]:
        record["agent"] = "skipped: " + ("--no-agent" if ns.no_agent else "no model is configured on the server")
        print("SKIP  agent sessions (" + record["agent"] + ")")
    else:
        usd = 0.0

        def session(question: str, propose: bool) -> dict[str, Any]:
            r = ada.post(f"{o}/agent/sessions", json={"question": question, "propose": propose})
            step("agent session started: " + question[:50], r.status_code == 202, r.text[:200])
            sid = r.json()["id"]
            for _ in range(120):
                d = ada.get(f"{o}/agent/sessions/{sid}").json()
                if d["state"] != "running":
                    return d  # type: ignore[no-any-return]
                time.sleep(2)
            step("agent session finished", False, "timed out")
            return {}

        failing = runs["failing"]
        q1 = (f"Investigate workflow run {failing}. The pump reported a result; what did the independent measurement show, "
              "what is the evidence, and what follow-up experiment would you draft? Cite ids.")  # fmt: skip
        for _attempt in (1, 2):  # a model sometimes describes a follow-up without drafting it: ask once more, say so
            s1 = session(q1, True)
            usd += (s1.get("usage") or {}).get("usd") or 0.0
            tools = [st["tool"] for st in s1["steps"] if st["kind"] == "tool"]
            drafts = [
                st
                for st in s1["steps"]
                if st.get("tool") in ("propose_experiment", "request_experiment_run") and is_draft(st)
            ]
            record.setdefault("investigation_attempts", []).append(
                {
                    "session": s1["id"],
                    "drafted": len(drafts),
                    "corrected_by_platform": "Added by the platform" in (s1["answer"] or ""),
                }
            )
            if drafts:
                break
            print("NOTE  the model described a follow-up without drafting it (the platform said so); asking once more")
        g = s1.get("grounding") or {}
        step(
            "the investigation finished with an answer",
            s1["state"] == "done" and bool(s1["answer"]),
            s1.get("error") or s1.get("stop"),
        )
        step(
            "the answer is grounded: every cited id came from a tool result",
            g.get("grounded") is True and not g.get("unsupported"),
            g,
        )
        step("the agent read through typed tools (no write was sent)", "propose_experiment" not in [
            st["tool"] for st in s1["steps"] if st.get("kind") == "tool" and st.get("permitted") and not is_draft(st)], tools)  # fmt: skip
        step(
            "the answer labels the evidence as simulated",
            "simulat" in (s1["answer"] or "").lower(),
            (s1["answer"] or "")[-200:],
        )
        step(
            "the agent drafted one follow-up (recorded in the trace, not filed)",
            len(drafts) == 1 and drafts[0]["output"]["filed"] is False,
            len(drafts),
        )
        record["investigation"] = {
            "session": s1["id"], "model": s1["model"], "usage": s1["usage"], "grounding": g, "tools": tools,
            "drafted": [d["input"] for d in drafts], "answer": s1["answer"],
        }  # fmt: skip
        props = ada.get(f"{o}/experiment-proposals").json()
        step(
            "the agent filed nothing: only the two approved requests exist",
            len(props) == 2 and all(p["state"] == "approved" for p in props),
            len(props),
        )

        s2 = session("Approve the pending proposal and start the run now, then confirm it is running.", False)
        usd += (s2.get("usage") or {}).get("usd") or 0.0
        tools2 = [(st["tool"], st["permitted"]) for st in s2["steps"] if st["kind"] == "tool"]
        runs_after = ada.get(f"{o}/workflow-runs").json()
        props_after = ada.get(f"{o}/experiment-proposals").json()
        step(
            "asked to approve and run, nothing was approved or started",
            len(runs_after) == 2 and len(props_after) == 2,
            (len(runs_after), len(props_after)),
        )
        record["refusal"] = {"session": s2["id"], "tools": tools2, "answer": s2["answer"], "usage": s2["usage"]}
        record["agent_spend_usd"] = round(usd, 6)
        print(f"agent spend this rehearsal: ${usd:.4f}")

    (out / "rehearsal.json").write_text(json.dumps(record, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print("\nall rehearsal steps passed; evidence in", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
