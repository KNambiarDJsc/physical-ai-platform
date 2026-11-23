"""A deterministic investigation of one workflow run: rules over what the platform stored, every finding citing the
ids of the stored evidence it rests on. It is a rule set, not a model: it never says more than the stored records say,
and it proposes nothing itself (it may SUGGEST an experiment; recording a proposal is a separate tool call)."""

from __future__ import annotations

from typing import Any


def _obs(v: dict[str, Any]) -> str:
    out = []
    for o in v.get("observed", []):
        out.append(f"{o['value']} {o.get('unit', '')}".strip() if isinstance(o, dict) and "value" in o else str(o))
    return ", ".join(out) or "nothing"


def investigate(run: dict[str, Any]) -> dict[str, Any]:
    rid = run["id"]
    findings: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []
    steps = run.get("steps", [])
    verification = run.get("verification") or {}
    report = verification.get("report") or {}
    conds = report.get("conditions") or []
    contract = (run.get("provenance") or {}).get("contract_sha256")
    claim = run.get("reported") or {}

    def add(sev: str, statement: str, evidence: list[str]) -> None:
        findings.append({"id": f"F{len(findings) + 1}", "severity": sev, "statement": statement, "evidence": evidence})

    state = run["state"]
    if state in ("failed", "outcome_unknown", "cancelled"):
        err = run.get("error") or {}
        bad = [s for s in steps if s["state"] in ("failed", "refused", "outcome_unknown")]
        ev = [f"run:{rid}"] + [f"step:{rid}/{s['position']}" for s in bad]
        add(
            "bad", f"The run ended {state}: {err.get('code', 'no error code')}: {err.get('message', 'no message')}.", ev
        )
        for s in bad:
            add(
                "bad",
                f"Step {s['position'] + 1} ({s['device']}.{s['action']}) is {s['state']}: "
                f"{s.get('error') or 'no detail'}.",
                [f"step:{rid}/{s['position']}"],
            )
    if run.get("outcome_class") == "contradiction":
        cond = next((c for c in conds if c["result"] != "TRUE"), conds[0] if conds else {})
        ev = [f"run:{rid}", f"verification:{rid}"] + ([f"contract:{contract[:12]}"] if contract else [])
        add(
            "bad",
            f"{claim.get('device', 'The instrument')} reported {claim.get('value')}, but the independent measurement "
            f"does not "
            f"support it: '{cond.get('name')}' is {str(cond.get('result', '')).lower()}, observed {_obs(cond)}.",
            ev,
        )
        suggestions.append(
            {
                "workflow": run["workflow"],
                "rationale": "Repeat the same workflow once: if the contradiction repeats, the cause is persistent "
                "(the "
                "instrument or its line), if it does not, it was transient. Evidence: " + ", ".join(ev),
            }
        )
    elif run.get("outcome_class") == "supported_success":
        add(
            "info",
            "The instrument's report and the independent measurement agree; the engine judged the contract satisfied.",
            [f"run:{rid}", f"verification:{rid}"],
        )
    if verification.get("verdict") == "UNKNOWN":
        reasons = ", ".join(f"{r['code']}" for r in report.get("reasons", [])) or "no reason given"
        add(
            "warn",
            f"The engine could not decide: {reasons}. Missing evidence is not success.",
            [f"run:{rid}", f"verification:{rid}"],
        )
    for s in steps:
        if s.get("dispatches", 0) > 1:
            add(
                "info",
                f"Step {s['position'] + 1} ({s['device']}.{s['action']}) was sent {s['dispatches']} times"
                f"{' (repeat-safe: the device ignores a repeated request id)' if s['idempotent'] else ''}.",
                [f"step:{rid}/{s['position']}"],
            )
    if not findings:
        add("info", f"The run is {state}; nothing in the stored records needs attention.", [f"run:{rid}"])
    return {
        "run": rid,
        "state": state,
        "method": "rule-based over stored records; not a model",
        "evidence_class": (run.get("provenance") or {}).get("evidence_class"),  # "simulated": say so when reporting
        "findings": findings,
        "suggested_experiments": suggestions,
    }
