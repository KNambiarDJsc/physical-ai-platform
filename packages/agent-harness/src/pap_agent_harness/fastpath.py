"""Deterministic fast paths for routine questions: answered by fixed tool calls and a template, with no model call and
no cost. Anything that does not match a fast path exactly goes to the agent. Every fast answer cites the ids it read."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .toolbox import Toolbox

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


@dataclass(frozen=True)
class FastPath:
    name: str
    pattern: re.Pattern[str]
    answer: Callable[[Toolbox, str, re.Match[str]], str]


def _run_status(tb: Toolbox, org: str, m: re.Match[str]) -> str:
    rid = m.group("id")
    res = tb.call("get_experiment_run", {"org": org, "request_id": rid})
    if "error" in res:
        return f"Could not read run {rid}: {res['error']}"
    d = res["result"]
    lines = [f"Run {rid} of {d.get('experiment_name')} version {d.get('version')}: {d.get('state')}, "
             f"{d.get('trials_done')} of {d.get('trials')} trials finished."]  # fmt: skip
    for t in d.get("trial_results", []):
        ms = ", ".join(f"{k} {v}" for k, v in (t.get("measurements") or {}).items()) or "no measurement"
        verdict = t.get("verdict") or "none"
        lines.append(f"- {t['arm']} trial {t['repetition'] + 1}: {t['state']}, engine verdict {verdict} "
                     f"({ms}) [run:{t['run_id']}]")  # fmt: skip
    lines.append(
        "Each verdict is one trial against its contract, not a release regression. (Answered without a model.)"
    )
    return "\n".join(lines)


def _experiments(tb: Toolbox, org: str, m: re.Match[str]) -> str:
    res = tb.call("list_experiments", {"org": org})
    if "error" in res:
        return f"Could not list experiments: {res['error']}"
    exps = res["result"]
    if not exps:
        return f"There are no experiments in {org} yet. (Answered without a model.)"
    out = [f"{len(exps)} experiment(s) in {org}:"]
    for e in exps:
        last = e["runs"][0] if e["runs"] else None
        state = (
            f"latest run {last['state']} ({last['trials_done']}/{last['trials']}) [request:{last['id']}]"
            if last
            else "not run"
        )
        out.append(f"- {e['name']} ({e['slug']}), {len(e['versions'])} version(s), {state}")
    return "\n".join([*out, "(Answered without a model.)"])


def _verdicts(tb: Toolbox, org: str, m: re.Match[str]) -> str:
    slug = m.group("slug")
    res = tb.call("list_release_verdicts", {"org": org, "experiment": slug})
    if "error" in res:
        return f"Could not read release verdicts of {slug}: {res['error']}"
    rows = res["result"]
    if not rows:
        return f"{slug} has not been judged as releases yet. (Answered without a model.)"
    out = [f"Release verdicts for {slug} (the engine's):"]
    for r in rows:
        v = r.get("verdict") or {}
        out.append(f"- version {r['version']}, {r['baseline_arm']} vs {r['candidate_arm']}: "
                   f"{v.get('verdict') or r['state']} ({'; '.join(v.get('reasons') or []) or 'no reasons'}) "
                   f"[evaluation:{r['evaluation_id']}]")  # fmt: skip
    return "\n".join([*out, "(Answered without a model.)"])


def _investigate(tb: Toolbox, org: str, m: re.Match[str]) -> str:
    """The platform's rule-based investigation of a laboratory run: what the stored records say, nothing more. This is
    the scripted fallback for the website: it needs no model, says it is rule-based, and cites every id it used."""
    rid = m.group("id")
    res = tb.call("investigate_run", {"org": org, "run_id": rid})
    if "error" in res:
        return f"Could not investigate run {rid}: {res['error']}"
    d = res["result"]
    lines = [f"Investigation of run {rid}: it ended {d['state']}. Method: {d['method']}."]
    if d.get("evidence_class") == "simulated":
        lines.append("The evidence is SIMULATED: it comes from a simulated instrument bench, not physical hardware.")
    cited: list[str] = []
    for f in d["findings"]:
        lines.append(f"- {f['id']} [{f['severity']}] {f['statement']} (evidence: {', '.join(f['evidence'])})")
        cited += [e for e in f["evidence"] if e not in cited]
    for s in (d.get("suggested_experiments") or [])[:1]:
        lines.append(f"Suggested follow-up: run the workflow {s['workflow']} once more. {s['rationale']}")
        if "propose_experiment" in tb.names():  # the person allowed drafts: record it; they decide whether to file it
            out = tb.call("propose_experiment", {"org": org, "workflow": s["workflow"],
                                                 "rationale": str(s["rationale"])[:2000], "evidence_ids": cited[:18]})  # fmt: skip  # noqa: E501
            drafted = isinstance(out.get("result"), dict) and out["result"].get("drafted")
            lines.append("It is recorded as a draft below for you to file." if drafted else "It could not be drafted.")
    lines.append("(Answered by fixed rules over stored records, without a model.)")
    return "\n".join(lines)


FAST_PATHS = (
    FastPath(
        "investigate_run",
        re.compile(rf"^\s*investigate\s+(workflow\s+)?run\s+(?P<id>{UUID})\s*[.?]?\s*$", re.I),
        _investigate,
    ),
    FastPath("run_status", re.compile(rf"^\s*(status of|show)\s+(run\s+)?(?P<id>{UUID})\s*\??\s*$", re.I), _run_status),
    FastPath("list_experiments", re.compile(r"^\s*(list|show)\s+(the\s+)?experiments\s*\??\s*$", re.I), _experiments),
    FastPath(
        "release_verdicts",
        re.compile(r"^\s*(release\s+)?verdicts?\s+(of|for)\s+(?P<slug>[a-z0-9][a-z0-9-]{0,62})\s*\??\s*$", re.I),
        _verdicts,
    ),
)


def try_fast_path(question: str, tb: Toolbox, org: str) -> tuple[str, str] | None:
    """(fast path name, answer) when the question is routine, else None."""
    for fp in FAST_PATHS:
        m = fp.pattern.match(question)
        if m:
            return fp.name, fp.answer(tb, org, m)
    return None
