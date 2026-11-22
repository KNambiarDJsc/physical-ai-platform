"""A deterministic explanation of one event in a recording: rules over what the platform stored (the decoded
track's event, the run identity, the bag summary, the linked episode's engine verdict), every finding citing the ids
of the stored evidence it rests on. Like ``investigate`` it is a rule set, not a model: it says no more than the
records say, it separates what the recording shows from what the engine decided, and it lists what is not known."""

from __future__ import annotations

from typing import Any

PROBLEM_KINDS = {"motion_continues", "motion_stopped_late", "applied_command_never_zero"}


def _short(sha: str | None) -> str:
    return (sha or "").removeprefix("sha256:")[:12]


def explain_event(rec: dict[str, Any], event_id: str, episode: dict[str, Any] | None) -> dict[str, Any]:
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

    if episode:
        report = episode.get("verifier_report") or {}
        contract = report.get("contract") or {}
        cond = (
            next((c for c in report.get("conditions", []) if c.get("result") != "TRUE"), None)
            or ((report.get("conditions") or [None])[0])
        )
        obs = ", ".join(f"{o['value']} {o.get('unit', '')}".strip() for o in (cond or {}).get("observed", []))
        link = rec["episode"]
        ids = [
            f"verification:{link['id']}",
            f"contract:{_short(contract.get('sha256'))}",
            f"evaluation:{link['evaluation_id']}",
        ]
        ev_class = (episode.get("document") or {}).get("evidence_class", "unknown")
        add(
            "bad" if episode["outcome_class"] == "verified_failure" else "info",
            f"The OpenMHS engine judged episode {link['episode_key']} ({link['release_label']}) "
            f"{str(episode['verdict']).lower()}: contract '{contract.get('name')}' v{contract.get('version')}"
            f"{', ' + repr(cond['name']) + ' is ' + str(cond['result']).lower() if cond else ''}"
            f"{', observed ' + obs if obs else ''}. Evidence class: {ev_class}. "
            f"Evidence digest {_short((report.get('evidence') or {}).get('sha256'))}.",
            ids,
        )
        if event["kind"] in PROBLEM_KINDS and episode["outcome_class"] == "verified_failure":
            add(
                "info",
                "The recording and the engine point the same way, by different measurements: this event is this "
                "reader's rule over the recorded messages, the verdict is the engine's over the episode's evidence "
                "file.",
                ids + ev_ids[2:],
            )
        elif event["kind"] in PROBLEM_KINDS:
            add(
                "warn",
                f"The recording shows a problem but the engine's outcome is {episode['outcome_class']}: the two do not "
                "agree and neither is overridden; the episode's evidence file and this recording measure differently.",
                ids + ev_ids[2:],
            )
        elif episode["outcome_class"] == "verified_failure":
            add(
                "warn",
                "The engine judged this episode a failure, but this event is not itself a problem; look at the events "
                "marked problem on the timeline.",
                ids,
            )
    else:
        not_known.append("the engine's verdict: this recording is not linked to an evaluated episode")

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
