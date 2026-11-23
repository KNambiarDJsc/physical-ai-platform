# ruff: noqa: E501 - the HTML template reads best with whole table rows on one line
"""A reproducible evidence report for one workflow run, built only from what the platform stored.

It formats; it never computes. The verdict, the contract and the measurements are the OpenMHS engine's and the
instruments' own records. There is no generation timestamp: the same run always produces the same bytes, so a report can
be checked later by regenerating it. Simulated evidence says so on its first line.
"""

from __future__ import annotations

import html
import json
from typing import Any

from .definition import definition_sha256

SCHEMA = "pap.lab-run-report/1"


def build(run: dict[str, Any], org: str, follow_ups: list[dict[str, Any]]) -> dict[str, Any]:
    """``run`` is a RunDetailOut dumped to JSON-compatible values; ``follow_ups`` are proposals that cite or started it."""
    prov = run.get("provenance") or {}
    ver = run.get("verification") or {}
    return {
        "schema": SCHEMA,
        "basis": "Stored platform records only. Nothing here is recomputed; the verdict is the OpenMHS engine's.",
        "organization": org,
        "evidence_class": prov.get("evidence_class"),
        "run": {
            k: run.get(k)
            for k in (
                "id",
                "workflow",
                "workflow_name",
                "environment",
                "state",
                "attempts",
                "submitted_by",
                "created_at",
                "started_at",
                "finished_at",
                "error",
            )
        },
        "procedure": {
            "definition_sha256": definition_sha256(run["definition"]),
            "steps": [
                {
                    "position": i,
                    "id": s["id"],
                    "device": s["device"],
                    "action": s["action"],
                    "input": s.get("input", {}),
                    "title": s.get("title", ""),
                }
                for i, s in enumerate(run["definition"].get("steps", []))
            ],
            "verification": run["definition"].get("verification"),
        },
        "execution": [
            {
                k: s.get(k)
                for k in (
                    "position",
                    "key",
                    "device",
                    "action",
                    "input",
                    "state",
                    "dispatches",
                    "request_id",
                    "idempotent",
                    "invocation_id",
                    "started_at",
                    "finished_at",
                    "output",
                    "error",
                )
            }
            for s in run.get("steps", [])
        ],
        "reported_by_instrument": run.get("reported"),
        "independently_verified": {
            "verdict": run.get("verdict"),
            "outcome_class": run.get("outcome_class"),
            "conditions": (ver.get("report") or {}).get("conditions", []),
            "evidence": ver.get("evidence", []),
            "contract": ver.get("contract"),
        },
        "provenance": prov,
        "follow_up_proposals": follow_ups,
    }


def to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str, ensure_ascii=False) + "\n"


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _j(v: Any) -> str:
    return html.escape(json.dumps(v, sort_keys=True, default=str, ensure_ascii=False))


CSS = """body{font:14px/1.5 system-ui,Segoe UI,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;color:#111418}
h1{font-size:1.4rem}h2{font-size:1.05rem;margin-top:1.8rem;border-bottom:1px solid #ccd;padding-bottom:.2rem}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid #dde1e6;vertical-align:top}
code,.num{font-family:ui-monospace,Consolas,monospace;font-size:12px;word-break:break-all}
.banner{background:#fbf1dc;color:#5c3b00;padding:.5rem .8rem;border-radius:4px;font-weight:600}
.bad{color:#9b2430;font-weight:600}.ok{color:#14603f;font-weight:600}.note{color:#525d6a;font-size:12px}"""


def to_html(r: dict[str, Any]) -> str:
    run, ver = r["run"], r["independently_verified"]
    sim = r.get("evidence_class") == "simulated"
    verdict_cls = "ok" if ver.get("verdict") == "SATISFIED" else "bad"
    rep = r.get("reported_by_instrument") or {}
    rows_steps = "".join(
        f"<tr><td>{_e(s['position'] + 1)}</td><td>{_e(s['device'])}.{_e(s['action'])}</td><td class=num>{_j(s['input'])}</td>"
        f"<td>{_e(s['state'])}</td><td class=num>{_e(s['dispatches'])}</td><td class=num>{_e(s['started_at'])}</td>"
        f"<td class=num>{_j(s['output'])}</td></tr>"
        for s in r["execution"]
    )
    rows_cond = (
        "".join(
            f"<tr><td>{_e(c.get('name'))}</td><td>{_e(c.get('result'))}</td><td class=num>{_j(c.get('observed'))}</td></tr>"
            for c in ver["conditions"]
        )
        or "<tr><td colspan=3>No conditions were recorded.</td></tr>"
    )
    rows_follow = (
        "".join(
            f"<tr><td class=num>{_e(p['id'])}</td><td>{_e(p['state'])}</td><td>{_e(p['proposed_by'])}</td>"
            f"<td>{_e(p.get('decided_by') or '—')}</td><td>{_e(p['rationale'])}</td><td class=num>{_e(', '.join(p.get('evidence_ids') or []))}</td></tr>"
            for p in r["follow_up_proposals"]
        )
        or "<tr><td colspan=6>None.</td></tr>"
    )
    prov = r.get("provenance") or {}
    eng = prov.get("engine") or {}
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Laboratory run {_e(run["id"])}</title>
<style>{CSS}</style></head><body>
<h1>Laboratory run evidence report</h1>
{'<p class="banner">SIMULATED EVIDENCE: produced by a simulated instrument bench. No physical hardware was involved.</p>' if sim else ""}
<p class="note">{_e(r["basis"])} Schema <code>{_e(r["schema"])}</code>. Same run, same bytes: there is no generation time.</p>
<h2>Run</h2>
<table><tr><th>Workflow</th><td>{_e(run["workflow_name"])} (<code>{_e(run["workflow"])}</code>)</td></tr>
<tr><th>Run id</th><td class=num>{_e(run["id"])}</td></tr><tr><th>Workspace</th><td>{_e(r["organization"])}</td></tr>
<tr><th>Environment</th><td>{_e(run["environment"])}</td></tr><tr><th>State</th><td>{_e(run["state"])}, {_e(run["attempts"])} attempt(s)</td></tr>
<tr><th>Started by</th><td>{_e(run["submitted_by"])}</td></tr><tr><th>Created</th><td class=num>{_e(run["created_at"])}</td></tr>
<tr><th>Finished</th><td class=num>{_e(run["finished_at"])}</td></tr></table>
<h2>Result</h2>
<table><tr><th>Reported by the instrument</th><td>{_e(rep.get("device"))}: {_e(rep.get("value"))} <span class=num>{_j(rep.get("output"))}</span></td></tr>
<tr><th>Independently verified (OpenMHS engine)</th><td class="{verdict_cls}">{_e(ver.get("verdict"))} &middot; {_e(ver.get("outcome_class"))}</td></tr></table>
<h2>Verification conditions</h2><table><tr><th>Condition</th><th>Result</th><th>Observed</th></tr>{rows_cond}</table>
<h2>Procedure and execution</h2>
<p class="note">Procedure digest <code>{_e(r["procedure"]["definition_sha256"])}</code></p>
<table><tr><th>#</th><th>Device action</th><th>Input</th><th>State</th><th>Sends</th><th>Started</th><th>Output</th></tr>{rows_steps}</table>
<h2>Provenance</h2>
<table><tr><th>Engine (pinned build)</th><td class=num>{_j(eng)}</td></tr>
<tr><th>Contract digest</th><td class=num>{_e(prov.get("contract_sha256"))}</td></tr>
<tr><th>Evidence digest</th><td class=num>{_e(prov.get("evidence_sha256"))}</td></tr>
<tr><th>Evidence class</th><td>{_e(prov.get("evidence_class"))}</td></tr></table>
<h2>Follow-up proposals that cite or started this run</h2>
<table><tr><th>Proposal</th><th>State</th><th>Proposed by</th><th>Decided by</th><th>Rationale</th><th>Evidence</th></tr>{rows_follow}</table>
</body></html>
"""
