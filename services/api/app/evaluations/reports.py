"""RI-008: a reproducible JSON report of one evaluation, and an HTML report rendered from that JSON only.

The JSON report is assembled from stored rows (the job, its releases, mapping, artifacts, the engine's outputs
byte for byte and the episode table) and serialized deterministically: no generation time, sorted keys, sorted
lists. Generating it twice gives identical bytes, so its sha256 identifies the report.

``render_html`` takes the parsed JSON report and nothing else: no session, no settings, no engine. Every figure in
it is an engine output read from ``engine_outputs[*].raw``; the HTML only formats numbers for display.
"""

from __future__ import annotations

import hashlib
import html
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..evidence.models import Artifact
from ..ingestion.models import MappingRevision
from ..organizations.models import Organization
from ..projects.models import Project
from ..releases.models import Release
from .models import EpisodeRecord, EvaluationJob, EvaluationResult, JobArtifact

SCHEMA = "pap.report/1"
NOTICE = (
    "Every statistic and verdict in this report was computed by the OpenMHS engine identified under provenance. "
    "The platform stores and displays the engine's outputs; it computes no statistic of its own."
)
EVIDENCE_NOTICE = {
    "synthetic": "SYNTHETIC EVIDENCE. Generated data, not recorded from any robot. It says nothing about the "
    "performance of any real system.",
    "simulated": "SIMULATED EVIDENCE. Recorded from a simulator. Conclusions do not transfer to hardware without "
    "physical validation.",
    "production": "PRODUCTION EVIDENCE. Recorded from deployed systems.",
}
COMPARISONS = ("compare_reported", "compare_verified", "compare_paired")


def build_report(session: Session, job: EvaluationJob) -> dict[str, Any]:
    """The JSON report as a dict. The caller has already checked tenancy and that the job succeeded."""
    project = session.get(Project, job.project_id)
    assert project is not None
    org = session.get(Organization, project.organization_id)
    assert org is not None
    pair = [job.baseline_release_id, job.candidate_release_id]
    rels = {r.id: r for r in session.scalars(select(Release).where(Release.id.in_(pair)))}
    mapping = session.get(MappingRevision, job.mapping_id)
    assert mapping is not None
    inputs = []
    for art, rel_id in session.execute(
        select(Artifact, JobArtifact.release_id)
        .join(JobArtifact, JobArtifact.artifact_id == Artifact.id)
        .where(JobArtifact.job_id == job.id)
    ):
        inputs.append(
            {
                "release": rels[rel_id].label,
                "artifact_id": str(art.id),
                "sha256": art.sha256,
                "filename": art.filename,
                "size_bytes": art.size_bytes,
                "media_type": art.media_type,
            }
        )
    inputs.sort(key=lambda a: (a["release"], a["sha256"]))
    outputs = {
        r.kind: {"raw": r.raw, "raw_sha256": r.raw_sha256}
        for r in session.scalars(select(EvaluationResult).where(EvaluationResult.job_id == job.id))
    }
    label = {rid: r.label for rid, r in rels.items()}
    episodes = [
        {
            "release": label[e.release_id],
            "episode_key": e.episode_key,
            "robot": e.robot,
            "site": e.site,
            "scenario": e.scenario,
            "task_type": e.task_type,
            "ended_at": e.ended_at,
            "reported": e.reported,
            "verdict": e.verdict,
            "outcome_class": e.outcome_class,
            "reasons": sorted(e.reasons),
            "source_sha256": str(e.document.get("source", {}).get("artifact_sha256", "")),
            "source_row": e.source_row,
        }
        for e in session.scalars(select(EpisodeRecord).where(EpisodeRecord.job_id == job.id))
    ]
    episodes.sort(key=lambda e: (e["release"], e["ended_at"], e["episode_key"]))

    def rel(rid: Any) -> dict[str, Any]:
        r = rels[rid]
        return {"id": str(r.id), "label": r.label, "kind": r.kind, "manifest_digest": r.manifest_digest}

    return {
        "schema": SCHEMA,
        "notice": NOTICE,
        "evidence_class": sorted((job.provenance or {}).get("evidence_class", [])),
        "evaluation": {
            "id": str(job.id),
            "organization": org.slug,
            "project": project.slug,
            "state": job.state,
            "config": job.config,
            "input_sha256": job.input_sha256,
            "attempts": job.attempts,
            "created_at": job.created_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        },
        "releases": {"baseline": rel(job.baseline_release_id), "candidate": rel(job.candidate_release_id)},
        "mapping": {
            "id": str(mapping.id),
            "name": mapping.name,
            "version": mapping.version,
            "spec_sha256": mapping.spec_sha256,
        },
        "inputs": inputs,
        "provenance": job.provenance,
        "summary": job.summary,
        "engine_outputs": outputs,
        "episodes": episodes,
    }


def serialize(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --- HTML, from the JSON report only -------------------------------------------------------------------------

VERDICT = {
    "improvement": "Improvement",
    "regression": "Regression",
    "no_change": "No change",
    "insufficient_evidence": "Insufficient evidence",
}
CLASS = {
    "supported_success": "Supported success",
    "verified_success": "Verified success",
    "verified_failure": "Verified failure",
    "contradiction": "Contradiction",
    "unknown": "Unknown",
    "reported_only": "Reported only",
    "insufficient_evidence": "Insufficient evidence",
}
TITLE = {
    "compare_reported": "As the robot reported",
    "compare_verified": "As independently verified",
    "compare_paired": "Paired by scenario",
}

CSS = """
:root{--ink:#16181d;--muted:#5b616e;--line:#d9dce3;--panel:#fff;--bg:#f6f7f9;--bad:#b42318;--ok:#067647;
--warn:#a15c07;--warn-bg:#fef0c7;--accent:#2b59c3}
@media (prefers-color-scheme:dark){:root{--ink:#e6e8ec;--muted:#9aa1ad;--line:#2e333d;--panel:#16191f;
--bg:#0e1014;--bad:#f97066;--ok:#47cd89;--warn:#fdb022;--warn-bg:#3a2a07;--accent:#84a9ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}h3{font-size:14px;margin:16px 0 6px}
.muted{color:var(--muted)}.num,code{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:12.5px}
.banner{border:1px solid var(--warn);background:var(--warn-bg);color:var(--warn);font-weight:600;padding:10px 14px;
border-radius:8px;margin:12px 0}.banner.production{border-color:var(--line);background:var(--panel);color:var(--ink)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;margin:10px 0}
.grid{display:grid;gap:10px}.grid>*{min-width:0}.card p{overflow-wrap:anywhere}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);
vertical-align:top}th{font-weight:600;color:var(--muted);font-size:12px}td.r,th.r{text-align:right}
.scroll{overflow-x:auto}.verdict{font-size:18px;font-weight:700}.regression{color:var(--bad)}
.improvement{color:var(--ok)}.insufficient_evidence{color:var(--warn)}.break{word-break:break-all}
ul{margin:4px 0;padding-left:20px}footer{margin-top:32px;font-size:12px}
@media print{body{background:#fff}.card{break-inside:avoid}}
"""


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def _pct(v: Any) -> str:
    return "—" if v is None else f"{float(v) * 100:.1f}%"


def _pp(v: Any) -> str:
    return "—" if v is None else f"{float(v) * 100:+.1f} pp"


def _interval(ci: Any, fmt: Any = _pct) -> str:
    return "—" if not ci else f"{fmt(ci[0])} to {fmt(ci[1])}"


def _table(head: list[str], rows: list[list[str]], right: set[int] | frozenset[int] = frozenset()) -> str:
    th = "".join(f'<th scope="col"{" class=r" if i in right else ""}>{_e(h)}</th>' for i, h in enumerate(head))
    body = "".join(
        "<tr>" + "".join(f"<td{' class="r num"' if i in right else ''}>{c}</td>" for i, c in enumerate(r)) + "</tr>"
        for r in rows
    )
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def _comparison(kind: str, c: dict[str, Any], labels: tuple[str, str]) -> str:
    v = c.get("verdict", "")
    diff = c.get("difference")
    arms = []
    for key, lab in zip(("a", "b"), labels, strict=True):
        a = c.get(key) or {}
        arms.append(
            [
                _e(lab),
                _e(a.get("unit")),
                _e(a.get("scenarios")),
                _e(a.get("failed")),
                _e(a.get("succeeded")),
                _e(a.get("unknown")),
                _pct(a.get("rate")),
                _interval(a.get("ci95")),
                _interval(a.get("unknown_bounds")),
            ]
        )
    parts = [
        f'<div class="card"><h3>{_e(TITLE.get(kind, kind))}</h3>',
        f'<div class="verdict {_e(v)}">{_e(VERDICT.get(v, v))}</div>',
        '<p class="muted">Failure-rate difference (candidate minus baseline): '
        f'<span class="num">{_pp(diff[0]) if diff else "—"}</span>, 95% interval '
        f'<span class="num">{_interval(diff[1:] if diff else None, _pp)}</span>'
        f" ({_e(c.get('difference_method'))}). If every unknown outcome went either way: "
        f'<span class="num">{_interval(c.get("unknown_bounds"), _pp)}</span>.</p>',
        _table(
            [
                "Release",
                "Unit",
                "Units",
                "Failed",
                "Succeeded",
                "Unknown",
                "Failure rate",
                "95% interval",
                "Rate if unknowns resolved",
            ],
            arms,
            right={2, 3, 4, 5, 6, 7, 8},
        ),
    ]
    p = c.get("paired")
    if p:
        parts.append(
            '<p class="muted">Pairs: '
            + ", ".join(
                f"{_e(k.replace('_', ' '))} <span class=num>{_e(p.get(k))}</span>"
                for k in ("pairs", "both_ok", "both_fail", "a_only_fails", "b_only_fails", "unknown_pairs")
            )
            + f"; McNemar p <span class=num>{_e(p.get('mcnemar_p'))}</span>.</p>"
        )
    if c.get("strata"):
        parts.append("<h3>By site</h3>")
        parts.append(
            _table(
                ["Site", "Baseline failed / units", "Candidate failed / units", "Difference", "95% interval"],
                [
                    [
                        _e(s.get("site")),
                        f"{_e(s['a'][0])} / {_e(s['a'][1])}",
                        f"{_e(s['b'][0])} / {_e(s['b'][1])}",
                        _pp(s["difference"][0]),
                        _interval(s["difference"][1:], _pp),
                    ]
                    for s in c["strata"]
                ],
                right={1, 2, 3, 4},
            )
        )
    for title, items in (("Engine reasons", c.get("reasons")), ("Engine warnings", c.get("warnings"))):
        if items:
            parts.append(f"<h3>{title}</h3><ul>" + "".join(f"<li>{_e(x)}</li>" for x in items) + "</ul>")
    parts.append("</div>")
    return "".join(parts)


def render_html(report: dict[str, Any]) -> str:
    """The HTML report. Its only input is the parsed JSON report."""
    if report.get("schema") != SCHEMA:
        raise ValueError(f"not a {SCHEMA} document")
    digest = sha256_bytes(serialize(report))
    ev = report["evaluation"]
    rels = report["releases"]
    labels = (rels["baseline"]["label"], rels["candidate"]["label"])
    classes = report.get("evidence_class") or ["unlabelled"]
    out = report["engine_outputs"]
    prov = report.get("provenance") or {}
    engine = prov.get("engine") or {}
    summary = report.get("summary") or {}

    banners = "".join(
        f'<div class="banner {_e(c)}" role="note">{_e(EVIDENCE_NOTICE.get(c, f"{c.upper()} EVIDENCE."))}</div>'
        for c in classes
    )
    comps = (
        "".join(_comparison(k, json.loads(out[k]["raw"]), labels) for k in COMPARISONS if k in out)
        or "<p>No comparison was stored.</p>"
    )

    names = sorted(
        {k for per in (summary.get("classes") or {}).values() for k in per},
        key=lambda n: (list(CLASS).index(n) if n in CLASS else len(CLASS), n),
    )
    class_rows = [
        [_e(CLASS.get(n, n))] + [_e((summary.get("classes") or {}).get(lab, {}).get(n, 0)) for lab in labels]
        for n in names
    ]
    attention = [e for e in report.get("episodes", []) if e["outcome_class"] in ("contradiction", "unknown")]
    att_rows = [
        [
            f"<span class=num>{_e(e['episode_key'])}</span>",
            _e(e["release"]),
            _e(e["robot"]),
            _e(e["scenario"]),
            _e(e["reported"]),
            _e(e["verdict"] or "—"),
            _e(CLASS.get(e["outcome_class"], e["outcome_class"])),
            _e(", ".join(e["reasons"]) or "—"),
            f"<span class=num>{_e(e['source_sha256'][:19])}… row {_e(e['source_row'])}</span>",
        ]
        for e in attention
    ]
    inputs = [
        [_e(i["release"]), _e(i["filename"]), f"<code class=break>{_e(i['sha256'])}</code>", _e(i["size_bytes"])]
        for i in report.get("inputs", [])
    ]
    prov_rows = [
        ["Engine", f"{_e(engine.get('version'))} at commit <code class=break>{_e(engine.get('commit'))}</code>"],
        ["Engine binary", f"<code class=break>{_e(engine.get('binary_sha256'))}</code>"],
        ["Rules version", _e(prov.get("rules_version"))],
        [
            "Mapping",
            f"{_e(report['mapping']['name'])} v{_e(report['mapping']['version'])} "
            f"<code class=break>{_e(report['mapping']['spec_sha256'])}</code>",
        ],
        ["Input checksum", f"<code class=break>{_e(ev['input_sha256'])}</code>"],
        ["Events bundle", f"<code class=break>{_e((prov.get('bundle') or {}).get('events'))}</code>"],
        ["Engine store", f"<code class=break>{_e((prov.get('bundle') or {}).get('engine_store'))}</code>"],
        ["Configuration", f"<code class=break>{_e(json.dumps(ev['config'], sort_keys=True))}</code>"],
    ] + [[f"Engine output {_e(k)}", f"<code class=break>{_e(v['raw_sha256'])}</code>"] for k, v in sorted(out.items())]

    title = f"{labels[0]} → {labels[1]}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="pap-report-sha256" content="{_e(digest)}">
<title>Release report: {_e(title)}</title><style>{CSS}</style></head>
<body><main>
<p class="muted">Release Intelligence report · {_e(ev["organization"])} / {_e(ev["project"])}</p>
<h1>{_e(title)}</h1>
<p class="muted">Evaluation <span class=num>{_e(ev["id"])}</span>, finished {_e(ev["finished_at"])}.
Evidence class: <strong>{_e(", ".join(classes))}</strong>.</p>
{banners}
<p>{_e(report["notice"])}</p>
<h2>Comparisons</h2>
<div class="grid">{comps}</div>
<h2>Episode outcomes</h2>
<p class="muted">{_e(summary.get("episodes"))} episodes; {_e(summary.get("rejected_rows"))} source rows rejected by the
mapping. Each episode is classed by comparing what the robot reported with what the independent evidence showed.</p>
{_table(["Outcome", labels[0], labels[1]], class_rows, right={1, 2})}
<h2>Contradictions and unknowns ({len(attention)})</h2>
{
        _table(
            ["Episode", "Release", "Robot", "Scenario", "Reported", "Verdict", "Outcome", "Verifier reasons", "Source"],
            att_rows,
        )
        if att_rows
        else "<p>None.</p>"
    }
<h2>Inputs</h2>
{_table(["Release", "File", "sha256", "Bytes"], inputs, right={3})}
<h2>Provenance</h2>
{_table(["", ""], prov_rows)}
<footer class="muted">Rendered from the JSON report <code class=break>{_e(digest)}</code> ({_e(report["schema"])}).
Regenerating that report from the same evaluation gives the same bytes.</footer>
</main></body></html>
"""
