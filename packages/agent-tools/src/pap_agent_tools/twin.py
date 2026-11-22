"""A deterministic explanation of one event in a recording: rules over what the platform stored (the decoded
track's event, the run identity, the bag summary, the linked episode's engine verdict), every finding citing the ids
of the stored evidence it rests on. Like ``investigate`` it is a rule set, not a model: it says no more than the
records say, it separates what the recording shows from what the engine decided, and it lists what is not known."""

from __future__ import annotations

from typing import Any

PROBLEM_KINDS = {"motion_continues", "motion_stopped_late", "applied_command_never_zero"}


def _short(sha: str | None) -> str:
    return (sha or "").removeprefix("sha256:")[:12]


def _judged(rec: dict[str, Any], episode: dict[str, Any] | None, run: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the engine judged, from the linked episode or the linked experiment trial (a workflow run)."""
    if episode:
        link = rec["episode"]
        report = episode.get("verifier_report") or {}
        return {
            "report": report,
            "verdict": episode["verdict"],
            "outcome_class": episode["outcome_class"],
            "evidence_class": (episode.get("document") or {}).get("evidence_class", "unknown"),
            "subject": f"episode {link['episode_key']} ({link['release_label']})",
            "basis": "the episode's evidence file",
            "ids": [
                f"verification:{link['id']}",
                f"contract:{_short((report.get('contract') or {}).get('sha256'))}",
                f"evaluation:{link['evaluation_id']}",
            ],
        }
    if run and run.get("verification"):
        link = rec["run"]
        report = run["verification"].get("report") or {}
        seed = f", seed {link['seed']}" if link.get("seed") is not None else ""
        where = f" of experiment {link['experiment_name']} v{link['version']}" if link.get("experiment") else ""
        return {
            "report": report,
            "verdict": run["verification"]["verdict"],
            "outcome_class": run.get("outcome_class"),
            "evidence_class": (run.get("provenance") or {}).get("evidence_class", "unknown"),
            "subject": f"trial {link.get('arm') or run['id']}{seed}{where}",
            "basis": "the measurements the simulation host reported for this trial",
            "ids": [
                f"verification:{run['id']}",
                f"contract:{_short((report.get('contract') or {}).get('sha256'))}",
                f"workflow-run:{run['id']}",
            ],
        }
    return None


def explain_event(
    rec: dict[str, Any], event_id: str, episode: dict[str, Any] | None, run: dict[str, Any] | None = None
) -> dict[str, Any]:
    rid = rec["id"]
    event = next((e for e in rec["events"] if e["id"] == event_id), None)
    if event is None:
        known = ", ".join(e["id"] for e in rec["events"]) or "none"
        raise LookupError(f"no event {event_id!r} in recording {rid}; its events are: {known}")
    findings: list[dict[str, Any]] = []
    not_known: list[str] = []

    def add(severity: str, statement: str, evidence: list[str]) -> None:
        findings.append(
            {"id": f"F{len(findings) + 1}", "severity": severity, "statement": statement, "evidence": evidence}
        )

    ev_ids = [f"recording:{rid}", f"recording-sha256:{_short(rec['sha256'])}", f"event:{rid}/{event['id']}"]
    detail = ", ".join(f"{k} {v}" for k, v in event["detail"].items() if v is not None)
    sev = "bad" if event["severity"] == "problem" else ("warn" if event["severity"] == "warning" else "info")
    add(
        sev,
        f"At {event['t']} s on the recording's {rec['clock']} clock: {event['title']}"
        f"{' (' + detail + ')' if detail else ''}. Rule: {event['rule']} Source: {', '.join(event['topics'])}.",
        ev_ids,
    )

    ident = rec.get("identity") or {}
    sw = ident.get("software") or {}
    if sw:
        state = "a clean checkout" if not sw.get("tree_dirty") else "a modified tree"
        files = f" ({', '.join(sw['changed_files'])})" if sw.get("changed_files") else ""
        note = f" {sw['note']}" if sw.get("note") else ""
        add(
            "info",
            f"The run was recorded from {sw.get('repository')} commit {str(sw.get('commit'))[:10]} on {state}{files}."
            f"{note} "
            "This identity was written by the run's own script and is shown as reported.",
            [f"identity:{ident.get('run_id', rid)}"],
        )
    else:
        not_known.append("which software produced this recording: no run identity was uploaded with it")

    clock = (rec.get("summary") or {}).get("clock") or {}
    notable = [e for e in rec["events"] if e["kind"] in ("clock_not_monotonic", "stale_interval", "joint_constant")]
    for n in notable:
        if n["id"] != event["id"]:
            add("warn", f"Evidence quality: {n['title']} at {n['t']} s. {n['rule']}", [f"event:{rid}/{n['id']}"])
    if clock and not clock.get("monotonic", True):
        not_known.append("exact message times inside the window where the clock moved backwards")

    judged = _judged(rec, episode, run)
    if judged:
        report, ids = judged["report"], judged["ids"]
        contract = report.get("contract") or {}
        cond = (
            next((c for c in report.get("conditions", []) if c.get("result") != "TRUE"), None)
            or ((report.get("conditions") or [None])[0])
        )
        obs = ", ".join(f"{o['value']} {o.get('unit', '')}".strip() for o in (cond or {}).get("observed", []))
        outcome = judged["outcome_class"]
        add(
            "bad" if outcome == "verified_failure" else "info",
            f"The OpenMHS engine judged {judged['subject']} {str(judged['verdict']).lower()}: contract "
            f"'{contract.get('name')}' v{contract.get('version')}"
            f"{', ' + repr(cond['name']) + ' is ' + str(cond['result']).lower() if cond else ''}"
            f"{', observed ' + obs if obs else ''}. Evidence class: {judged['evidence_class']}. "
            f"Evidence digest {_short((report.get('evidence') or {}).get('sha256'))}.",
            ids,
        )
        if event["kind"] in PROBLEM_KINDS and outcome == "verified_failure":
            add(
                "info",
                "The recording and the engine point the same way, by different measurements: this event is this "
                "reader's rule over the recorded messages, the verdict is the engine's over " + judged["basis"] + ".",
                ids + ev_ids[2:],
            )
        elif event["kind"] in PROBLEM_KINDS:
            add(
                "warn",
                f"The recording shows a problem but the engine's outcome is {outcome}: the two do not "
                f"agree and neither is overridden; {judged['basis']} and this recording measure differently.",
                ids + ev_ids[2:],
            )
        elif outcome == "verified_failure":
            add(
                "warn",
                "The engine judged this a failure, but this event is not itself a problem; look at the events "
                "marked problem on the timeline.",
                ids,
            )
    else:
        not_known.append(
            "the engine's verdict: this recording is not linked to an evaluated episode or an experiment trial"
        )

    not_known.append(
        "why it happened: the recording shows what the base did, not the cause (no node logs or controller state)"
    )
    not_known.append("whether the same happens on physical hardware: the recording is simulated")
    return {
        "recording": {"id": rid, "label": rec["label"], "sha256": rec["sha256"], "clock": rec["clock"]},
        "event": {k: event[k] for k in ("id", "t", "kind", "severity", "title")},
        "findings": findings,
        "not_known": not_known,
        "basis": "rule-based over stored records; no language model was used",
    }
