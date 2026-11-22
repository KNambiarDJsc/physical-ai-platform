"""Judge two setups of an experiment as releases (SIM-007): from contract violations to a release verdict.

A violated trial is one run breaking the contract. Whether the candidate is a regression, an improvement or neither is
a statistical claim, and the platform already has exactly one place that makes it: Release Intelligence, with the
engine's ``ops compare``. This module does not compute anything. It writes the finished trials of one experiment
version (every approved run of it, so evidence accumulates run after run) for a baseline and a candidate setup as two
CSV evidence files, one row per trial with the host's raw measurements, declares the two setups as releases, generates
the evidence mapping from the spec's own contract, and submits an ordinary evaluation job. The worker and the pinned
engine do the rest, exactly as for uploaded evidence, and the verdict (often "insufficient evidence" for few trials)
is the engine's.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from openmhs_bridge import digest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import OrgContext
from ..config import Settings
from ..contracts.episode import EvaluationConfig
from ..contracts.mapping import MappingSpec
from ..engine import get_engine
from ..evaluations import service as evaluations
from ..evaluations.models import EvaluationJob, EvaluationResult
from ..evidence.models import Artifact
from ..evidence.storage import Storage
from ..ingestion.models import MappingRevision
from ..projects.models import Project
from ..releases.models import Release
from ..releases.routes import ReleaseIn, build_manifest
from ..workflows.models import WorkflowRun, WorkflowStep
from .compile import _evidence_name
from .host import SpecError
from .models import Experiment, ExperimentRequest, ExperimentTrial, ExperimentVersion
from .spec import ExperimentSpec

FINAL = ("succeeded", "failed", "outcome_unknown")
CLOCK = "pap-worker"


def _iso(t: Any) -> str:
    return t.isoformat().replace("+00:00", "Z") if t else ""


def trial_rows(session: Session, v: ExperimentVersion, arm: str, measurements: list[str]) -> list[dict[str, Any]]:
    """One row per finished trial of this version and arm, across every approved run of it. A trial that measured
    nothing (its run failed) is a row with blank measurements: the engine counts it as unknown, never as a pass."""
    rows = session.execute(
        select(ExperimentTrial, WorkflowRun)
        .join(ExperimentRequest, ExperimentRequest.id == ExperimentTrial.request_id)
        .join(WorkflowRun, WorkflowRun.id == ExperimentTrial.run_id)
        .where(
            ExperimentRequest.version_id == v.id,
            ExperimentRequest.state == "approved",
            ExperimentTrial.arm == arm,
            WorkflowRun.state.in_(FINAL),
        )
        .order_by(WorkflowRun.finished_at, WorkflowRun.id)
    ).all()
    out = []
    for t, run in rows:
        step = session.scalar(select(WorkflowStep).where(WorkflowStep.run_id == run.id).order_by(WorkflowStep.position))
        res = step.output if step is not None and step.state == "completed" and isinstance(step.output, dict) else {}
        raw_m = res.get("measurements")
        m: dict[str, Any] = raw_m if isinstance(raw_m, dict) else {}
        row: dict[str, Any] = {
            "episode_id": str(run.id),
            "arm": arm,
            "repetition": t.repetition,
            "seed": "" if t.seed is None else t.seed,
            "run_state": run.state,
            "ended_utc": _iso(run.finished_at),
            "reported_status": "",  # no controller report: the host only says the scenario ran
            "host_run_id": res.get("run_id", ""),
        }
        for name in measurements:
            v_ = m.get(name)
            row[name] = "" if v_ is None or isinstance(v_, bool) else v_
        out.append(row)
    return out


def to_csv(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def mapping_for(spec: ExperimentSpec, scenario: dict[str, Any], exp: Experiment, number: int) -> MappingSpec:
    """The evidence mapping, generated from the spec's own contract: the same conditions the trials were judged by."""
    outputs = {o["name"]: o for o in scenario.get("outputs", [])}
    used = list(dict.fromkeys(c.measurement for c in spec.contract.conditions))
    names = {m: _evidence_name(m, i) for i, m in enumerate(used)}
    time = {"column": "ended_utc", "format": "rfc3339", "clock_domain": CLOCK, "uncertainty_ms": 1000}

    def operand(x: Any, unit: str | None) -> Any:
        return {"value": x, "unit": unit} if unit and isinstance(x, int | float) and not isinstance(x, bool) else x

    conditions = []
    for c in spec.contract.conditions:
        unit = outputs[c.measurement].get("unit")
        cond: dict[str, Any] = {"name": c.name, "evidence": names[c.measurement], "op": c.op}
        if c.op == "between":
            cond["min"], cond["max"] = operand(c.min, unit), operand(c.max, unit)
        elif c.op == "in":
            cond["values"] = c.values
        else:
            cond["value"] = operand(c.value, unit)
        conditions.append(cond)
    measures: list[dict[str, Any]] = [
        {
            k: val
            for k, val in {
                "name": names[m],
                "column": m,
                "signal": f"sim.{m}",
                "unit": outputs[m].get("unit"),
                "kind": "independent_sensor",
                "system": spec.simulator.kind,
                "device": "simulation-host",
                "time": time,
            }.items()
            if val is not None
        }
        for m in used
    ]
    doc: dict[str, Any] = {
        "schema": "pap.mapping/1",
        "name": f"experiment-{exp.slug}-v{number}"[:120],
        "description": (
            f"Generated from experiment '{exp.name}' version {number} ({spec.scenario.id} v{spec.scenario.version} on "
            f"{spec.simulator.name}): one row per trial, the host's raw measurements, judged by the experiment's own "
            "contract. SIMULATED evidence. Times are when the worker recorded the trial's end."
        ),
        "evidence_class": "simulated",
        "input": {"format": "csv"},
        "episode_id": {"column": "episode_id"},
        "robot": {"const": f"sim/{spec.simulator.kind}"},
        "task_type": {"const": spec.scenario.id},
        "site": {"const": spec.environment},
        "ended_at": time,
        "reported_outcome": {
            "column": "reported_status",
            "values": {"succeeded": "succeeded", "failed": "failed"},
            "missing": "unknown",
        },
        "measurements": measures,
        "contract": {
            "name": spec.contract.name,
            "version": spec.contract.version,
            "window_ms": [0, 5000],
            "max_clock_uncertainty_ms": 5000,
            "conditions": conditions,
        },
    }
    return MappingSpec.model_validate(doc)


def _release(
    session: Session, project: Project, label: str, components: list[dict[str, Any]], description: str, actor: str
) -> Release:
    existing = session.scalar(select(Release).where(Release.project_id == project.id, Release.label == label))
    body = ReleaseIn(label=label, kind="software", components=components, description=description)
    manifest = build_manifest(body)
    if existing is not None:
        if existing.manifest_digest != digest(manifest):
            raise SpecError(409, "experiment.release_label", f"a different release is already called {label}")
        return existing
    r = Release(
        project_id=project.id, label=label, kind="software", description=description, manifest=manifest,
        manifest_digest=digest(manifest), created_by=actor,
    )  # fmt: skip
    session.add(r)
    session.flush()
    return r


def _artifact(session: Session, storage: Storage, project: Project, data: bytes, filename: str, actor: str) -> Artifact:
    stored = storage.put([data], len(data) + 1)
    existing = session.scalar(
        select(Artifact).where(Artifact.project_id == project.id, Artifact.sha256 == stored.sha256)
    )
    if existing is not None:
        return existing
    a = Artifact(
        project_id=project.id, sha256=stored.sha256, size_bytes=stored.size, media_type="text/csv", filename=filename,
        storage_key=stored.key, kind="source", created_by=actor,
    )  # fmt: skip
    session.add(a)
    session.flush()
    return a


def _mapping(session: Session, project: Project, spec: MappingSpec, actor: str) -> MappingRevision:
    doc = spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    sha = digest(doc)
    latest = session.scalar(
        select(MappingRevision)
        .where(MappingRevision.project_id == project.id, MappingRevision.name == spec.name)
        .order_by(MappingRevision.version.desc())
        .limit(1)
    )
    if latest is not None and latest.spec_sha256 == sha:
        return latest
    n = session.scalar(
        select(func.max(MappingRevision.version)).where(
            MappingRevision.project_id == project.id, MappingRevision.name == spec.name
        )
    )
    m = MappingRevision(
        project_id=project.id, name=spec.name, version=int(n or 0) + 1, spec=doc, spec_sha256=sha, created_by=actor
    )
    session.add(m)
    session.flush()
    return m


def judge_as_releases(
    session: Session,
    settings: Settings,
    storage: Storage,
    ctx: OrgContext,
    exp: Experiment,
    v: ExperimentVersion,
    baseline_arm: str,
    candidate_arm: str,
    project_slug: str | None,
) -> tuple[EvaluationJob, bool, dict[str, int]]:
    spec = ExperimentSpec.model_validate(v.spec)
    arms = {a.key: a for a in spec.arms}
    if baseline_arm not in arms or candidate_arm not in arms or baseline_arm == candidate_arm:
        raise SpecError(422, "experiment.arms", "choose two different setups of this version")
    slug = project_slug or (spec.model.project if spec.model else None)
    if not slug:
        raise SpecError(
            422, "experiment.project", "choose the project whose Release Intelligence should hold the verdict"
        )
    project = session.scalar(select(Project).where(Project.organization_id == ctx.org.id, Project.slug == slug))
    if project is None:
        raise SpecError(404, "not_found", "project not found")
    measurements = list(
        dict.fromkeys([*spec.observations.measurements, *(c.measurement for c in spec.contract.conditions)])
    )
    columns = [
        "episode_id",
        "arm",
        "repetition",
        "seed",
        "run_state",
        "ended_utc",
        "reported_status",
        "host_run_id",
        *measurements,
    ]
    actor = ctx.principal.label
    rel: dict[str, Release] = {}
    arts: dict[str, Artifact] = {}
    counts: dict[str, int] = {}
    for role, key in (("baseline", baseline_arm), ("candidate", candidate_arm)):
        rows = trial_rows(session, v, key, measurements)
        if not rows:
            raise SpecError(
                409,
                "experiment.no_trials",
                f"setup {key} has no finished trial in an approved run of version {v.number}",
            )
        counts[role] = len(rows)
        a = arms[key]
        params = {**spec.initial_conditions, **a.parameters}
        components: list[dict[str, Any]] = [
            *({"kind": "software", "name": s.name, "version": s.revision} for s in spec.software),
            {
                "kind": "config",
                "name": f"{spec.scenario.id} v{spec.scenario.version} setup {key}",
                "parameters": params,
            },
        ]
        rel[role] = _release(
            session,
            project,
            f"{exp.slug}-v{v.number}-{key}"[:100],
            components,
            f"Setup '{a.title or key}' of experiment '{exp.name}' version {v.number} ({v.spec_sha256}).",
            actor,
        )
        arts[role] = _artifact(
            session, storage, project, to_csv(rows, columns), f"{exp.slug}-v{v.number}-{key}.csv", actor
        )
    mapping = _mapping(session, project, mapping_for(spec, v.scenario, exp, v.number), actor)
    try:
        job, created = evaluations.submit(
            session,
            project,
            baseline_release_id=rel["baseline"].id,
            candidate_release_id=rel["candidate"].id,
            mapping_id=mapping.id,
            baseline_artifact_ids=[arts["baseline"].id],
            candidate_artifact_ids=[arts["candidate"].id],
            config=EvaluationConfig(task_type=spec.scenario.id, paired=False, stratify_by_site=False),
            engine_sha256=get_engine().config.expected_sha256,
            actor=actor,
            max_attempts=settings.job_max_attempts,
        )
    except evaluations.SubmissionError as e:
        raise SpecError(e.status, e.code, e.message) from e
    return job, created, counts


def verdict_of(session: Session, job: EvaluationJob) -> dict[str, Any] | None:
    """The engine's comparison verdict on independent evidence (else on reported outcomes), verbatim."""
    if job.state != "succeeded":
        return None
    res = {r.kind: r for r in session.scalars(select(EvaluationResult).where(EvaluationResult.job_id == job.id))}
    r = res.get("compare_verified") or res.get("compare_reported")
    if r is None:
        return None
    p = r.payload if isinstance(r.payload, dict) else json.loads(r.raw)
    return {"basis": r.kind, "verdict": p.get("verdict"), "reasons": p.get("reasons") or [], "raw_sha256": r.raw_sha256}
