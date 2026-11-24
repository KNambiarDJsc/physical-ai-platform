"""Experiments API: simulated environments and their scenarios, immutable versions, requests, decisions, results.

Approving queues ordinary workflow runs; the worker executes them. The API never commands a device.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import SLUG, EngineerDep, OrgContext, ViewerDep, audit_allow, error
from ..config import get_settings
from ..db import get_session
from ..evidence.storage import Storage, get_storage
from ..hardware.models import Device, Environment
from ..workflows.models import WorkflowRun
from .host import HOST, SpecError, read_listing, scenario_digest, simulator_ref
from .models import Experiment, ExperimentEvaluation, ExperimentRequest, ExperimentTrial, ExperimentVersion
from .releases import judge_as_releases, verdict_of
from .service import approve, arm_summary, create_version, principal_key, reject, request_run, trial_view
from .spec import SHA, ExperimentSpec

router = APIRouter(prefix="/api/v1/orgs/{org_slug}", tags=["experiments"])
SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[Storage, Depends(get_storage)]


def _raise(e: SpecError) -> Exception:
    return error(e.status, e.code, e.message)


# ------------------------------------------------------------------------------------------- environments


class SimScenarioOut(BaseModel):
    id: str
    version: str
    title: str
    description: str
    parameters_schema: dict[str, Any]
    outputs: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    max_duration_s: float
    definition_sha256: str


class SimEnvironmentOut(BaseModel):
    slug: str
    name: str
    state: Literal["ready", "no_host", "unreachable", "unavailable", "invalid"]
    message: str | None = None
    simulator: dict[str, Any] | None = None
    simulator_description: str | None = None
    scenarios: list[SimScenarioOut] = Field(default_factory=list)
    last_discovered_at: datetime | None = None


def _sim_env(session: Session, env: Environment) -> SimEnvironmentOut:
    base = dict(slug=env.slug, name=env.name, last_discovered_at=env.last_discovered_at)
    try:
        listing = read_listing(session, env, get_settings())
    except SpecError as e:
        state: Any = {
            "experiment.no_host": "no_host",
            "experiment.host_unreachable": "unreachable",
            "experiment.environment_unavailable": "unavailable",
        }.get(e.code, "invalid")
        return SimEnvironmentOut(**base, state=state, message=e.message)
    return SimEnvironmentOut(
        **base,
        state="ready",
        simulator=simulator_ref(listing.simulator),
        simulator_description=str(listing.simulator.get("description") or ""),
        scenarios=[
            SimScenarioOut(
                id=s["id"],
                version=s["version"],
                title=s.get("title") or s["id"],
                description=s.get("description") or "",
                parameters_schema=s.get("parameters_schema") or {},
                outputs=s.get("outputs") or [],
                artifacts=s.get("artifacts") or [],
                max_duration_s=float(s.get("max_duration_s") or 0),
                definition_sha256=scenario_digest(s),
            )
            for s in listing.scenarios
        ],
    )


@router.get("/simulation-environments")
def list_sim_environments(ctx: ViewerDep, session: SessionDep) -> list[SimEnvironmentOut]:
    """Simulated environments that have a discovered simulation host, with what the host lists now."""
    envs = session.scalars(
        select(Environment)
        .join(Device, Device.environment_id == Environment.id)
        .where(Environment.organization_id == ctx.org.id, Environment.kind == "simulated", Device.key == HOST)
        .order_by(Environment.slug)
    ).all()
    return [_sim_env(session, e) for e in envs]


# ------------------------------------------------------------------------------------------- experiments


class ExperimentCreateIn(BaseModel):
    slug: str = Field(pattern=SLUG)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class ExperimentVersionIn(BaseModel):
    spec: dict[str, Any]
    notes: str = Field(default="", max_length=2000)


class ExperimentVersionOut(BaseModel):
    number: int
    spec: dict[str, Any]
    spec_sha256: str
    scenario: dict[str, Any]
    notes: str
    environment: str
    created_by: str
    created_at: datetime


class ExperimentRequestOut(BaseModel):
    id: uuid.UUID
    experiment: str
    experiment_name: str
    version: int
    spec_sha256: str
    state: str
    requested_by: str
    requested_by_me: bool
    note: str
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str
    created_at: datetime
    trials: int
    trials_done: int


class ExperimentOut(BaseModel):
    slug: str
    name: str
    description: str
    created_by: str
    created_at: datetime
    versions: list[ExperimentVersionOut]
    requests: list[ExperimentRequestOut]


class ExperimentRequestIn(BaseModel):
    note: str = Field(default="", max_length=2000)


class ExperimentDecisionIn(BaseModel):
    spec_sha256: str = Field(pattern=SHA, description="The checksum of the version the decider reviewed.")
    note: str = Field(default="", max_length=2000)


class TrialArtifactOut(BaseModel):
    name: str
    state: Literal["stored", "rejected"]
    filename: str | None = None
    media_type: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    error: str | None = None


class TrialResultOut(BaseModel):
    """One trial: what the host measured, the engine's verdict, and what was captured. Nothing is derived."""

    id: uuid.UUID
    arm: str
    repetition: int
    seed: int | None
    run_id: uuid.UUID
    state: str
    step_state: str | None
    verdict: str | None
    error: dict[str, Any] | None
    measurements: dict[str, Any] | None
    host_run: dict[str, Any] | None
    capture_state: str
    capture_error: str | None
    artifacts: list[TrialArtifactOut]
    recording_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None


class ArmSummaryOut(BaseModel):
    """Raw values and verdict counts for one arm. No statistic: that is the engine's `ops compare`."""

    arm: str
    title: str
    role: Literal["baseline", "candidate"]
    parameters: dict[str, Any]
    trials: int
    states: dict[str, int]
    verdicts: dict[str, int]
    values: dict[str, list[Any]]


class ExperimentRequestDetail(ExperimentRequestOut):
    spec: dict[str, Any]
    scenario: dict[str, Any]
    environment: str
    arms: list[ArmSummaryOut]
    trial_results: list[TrialResultOut]


def _version_out(session: Session, v: ExperimentVersion) -> ExperimentVersionOut:
    env = session.get(Environment, v.environment_id)
    assert env is not None
    return ExperimentVersionOut(
        number=v.number,
        spec=v.spec,
        spec_sha256=v.spec_sha256,
        scenario=v.scenario,
        notes=v.notes,
        environment=env.slug,
        created_by=v.created_by,
        created_at=v.created_at,
    )


def _request_out(session: Session, r: ExperimentRequest, ctx: OrgContext) -> ExperimentRequestOut:
    v = session.get(ExperimentVersion, r.version_id)
    assert v is not None
    e = session.get(Experiment, v.experiment_id)
    assert e is not None
    trials = session.scalars(select(ExperimentTrial).where(ExperimentTrial.request_id == r.id)).all()
    done = sum(
        1 for t in trials if (run := session.get(WorkflowRun, t.run_id)) is not None and run.finished_at is not None
    )
    return ExperimentRequestOut(
        id=r.id,
        experiment=e.slug,
        experiment_name=e.name,
        version=v.number,
        spec_sha256=r.spec_sha256,
        state=r.state,
        requested_by=r.requested_by,
        requested_by_me=r.requested_by_id == principal_key(ctx),
        note=r.note,
        decided_by=r.decided_by,
        decided_at=r.decided_at,
        decision_note=r.decision_note,
        created_at=r.created_at,
        trials=len(trials),
        trials_done=done,
    )


def _experiment(session: Session, org_id: uuid.UUID, slug: str) -> Experiment:
    e = session.scalar(select(Experiment).where(Experiment.organization_id == org_id, Experiment.slug == slug))
    if e is None:
        raise error(404, "not_found", "experiment not found")
    return e


def _version(session: Session, e: Experiment, number: int) -> ExperimentVersion:
    v = session.scalar(
        select(ExperimentVersion).where(ExperimentVersion.experiment_id == e.id, ExperimentVersion.number == number)
    )
    if v is None:
        raise error(404, "not_found", "version not found")
    return v


def _request(session: Session, org_id: uuid.UUID, rid: uuid.UUID, *, decision: bool = False) -> ExperimentRequest:
    query = select(ExperimentRequest).where(ExperimentRequest.organization_id == org_id, ExperimentRequest.id == rid)
    r = session.scalar(query.with_for_update() if decision else query)
    if r is None:
        raise error(404, "not_found", "request not found")
    return r


@router.post("/experiments", status_code=201)
def create_experiment(body: ExperimentCreateIn, ctx: EngineerDep, session: SessionDep) -> ExperimentOut:
    e = Experiment(
        organization_id=ctx.org.id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        created_by=ctx.principal.label,
    )
    session.add(e)
    try:
        session.flush()
    except IntegrityError as ex:
        session.rollback()
        raise error(409, "conflict", "an experiment with that slug exists in this workspace") from ex
    audit_allow(session, ctx, "experiment.create", f"experiment:{e.id}")
    session.commit()
    return get_experiment(e.slug, ctx, session)


@router.get("/experiments")
def list_experiments(ctx: ViewerDep, session: SessionDep) -> list[ExperimentOut]:
    rows = session.scalars(
        select(Experiment).where(Experiment.organization_id == ctx.org.id).order_by(Experiment.created_at.desc())
    ).all()
    return [get_experiment(e.slug, ctx, session) for e in rows]


@router.get("/experiments/{experiment_slug}")
def get_experiment(
    experiment_slug: Annotated[str, Path(pattern=SLUG)], ctx: ViewerDep, session: SessionDep
) -> ExperimentOut:
    e = _experiment(session, ctx.org.id, experiment_slug)
    versions = session.scalars(
        select(ExperimentVersion).where(ExperimentVersion.experiment_id == e.id).order_by(ExperimentVersion.number)
    ).all()
    reqs = session.scalars(
        select(ExperimentRequest)
        .where(ExperimentRequest.version_id.in_([v.id for v in versions]))
        .order_by(ExperimentRequest.created_at.desc())
    ).all()
    return ExperimentOut(
        slug=e.slug,
        name=e.name,
        description=e.description,
        created_by=e.created_by,
        created_at=e.created_at,
        versions=[_version_out(session, v) for v in versions],
        requests=[_request_out(session, r, ctx) for r in reqs],
    )


@router.post(
    "/experiments/{experiment_slug}/versions",
    status_code=201,
    responses={200: {"description": "this exact specification is already a version"}},
)
def create_experiment_version(
    experiment_slug: Annotated[str, Path(pattern=SLUG)],
    body: ExperimentVersionIn,
    ctx: EngineerDep,
    session: SessionDep,
    response: Response,
) -> ExperimentVersionOut:
    """Validate a spec against what the host lists now and store it as an immutable version (checksum computed here)."""
    e = _experiment(session, ctx.org.id, experiment_slug)
    try:
        v, created = create_version(session, get_settings(), ctx, e, body.spec, body.notes)
    except SpecError as ex:
        raise _raise(ex) from ex
    if created:
        audit_allow(session, ctx, "experiment.version", f"experiment:{e.id}", number=v.number, sha256=v.spec_sha256)
        session.commit()
    else:
        response.status_code = 200
    return _version_out(session, v)


@router.get("/experiments/{experiment_slug}/versions/{number}")
def get_experiment_version(
    experiment_slug: Annotated[str, Path(pattern=SLUG)],
    number: Annotated[int, Path(ge=1)],
    ctx: ViewerDep,
    session: SessionDep,
) -> ExperimentVersionOut:
    return _version_out(session, _version(session, _experiment(session, ctx.org.id, experiment_slug), number))


@router.post("/experiments/{experiment_slug}/versions/{number}/requests", status_code=201)
def request_experiment_run(
    experiment_slug: Annotated[str, Path(pattern=SLUG)],
    number: Annotated[int, Path(ge=1)],
    body: ExperimentRequestIn,
    ctx: ViewerDep,
    session: SessionDep,
) -> ExperimentRequestOut:
    """Ask for a run of one version. This queues nothing: an approval of this exact checksum does."""
    v = _version(session, _experiment(session, ctx.org.id, experiment_slug), number)
    r = request_run(session, ctx, v, body.note)
    audit_allow(session, ctx, "experiment.request", f"experiment_request:{r.id}", sha256=v.spec_sha256)
    session.commit()
    return _request_out(session, r, ctx)


@router.get("/experiment-requests")
def list_experiment_requests(
    ctx: ViewerDep,
    session: SessionDep,
    state: Annotated[Literal["awaiting_approval", "approved", "rejected"] | None, Query()] = None,
) -> list[ExperimentRequestOut]:
    q = select(ExperimentRequest).where(ExperimentRequest.organization_id == ctx.org.id)
    if state:
        q = q.where(ExperimentRequest.state == state)
    rows = session.scalars(q.order_by(ExperimentRequest.created_at.desc()).limit(200)).all()
    return [_request_out(session, r, ctx) for r in rows]


@router.get("/experiment-requests/{request_id}")
def get_experiment_request(request_id: uuid.UUID, ctx: ViewerDep, session: SessionDep) -> ExperimentRequestDetail:
    r = _request(session, ctx.org.id, request_id)
    v = session.get(ExperimentVersion, r.version_id)
    assert v is not None
    spec = ExperimentSpec.model_validate(v.spec)
    trials = session.scalars(
        select(ExperimentTrial)
        .where(ExperimentTrial.request_id == r.id)
        .order_by(ExperimentTrial.arm, ExperimentTrial.repetition)
    ).all()
    views = [trial_view(session, t, spec) for t in trials]
    order = {a.key: i for i, a in enumerate(spec.arms)}
    views.sort(key=lambda t: (order.get(t["arm"], 99), t["repetition"]))
    base = _request_out(session, r, ctx)
    return ExperimentRequestDetail(
        **base.model_dump(),
        spec=v.spec,
        scenario=v.scenario,
        environment=_version_out(session, v).environment,
        arms=arm_summary(spec, views),
        trial_results=views,
    )


@router.post("/experiment-requests/{request_id}/approve")
def approve_experiment_request(
    request_id: uuid.UUID, body: ExperimentDecisionIn, ctx: EngineerDep, session: SessionDep
) -> ExperimentRequestDetail:
    """Approve the exact checksum reviewed: re-check against the host, compile to workflows, queue every trial."""
    r = _request(session, ctx.org.id, request_id, decision=True)
    try:
        trials = approve(session, get_settings(), ctx, r, body.spec_sha256, body.note)
    except SpecError as ex:
        session.rollback()
        raise _raise(ex) from ex
    audit_allow(
        session, ctx, "experiment.approve", f"experiment_request:{r.id}", sha256=r.spec_sha256, trials=len(trials)
    )
    session.commit()
    return get_experiment_request(request_id, ctx, session)


@router.post("/experiment-requests/{request_id}/reject")
def reject_experiment_request(
    request_id: uuid.UUID, body: ExperimentDecisionIn, ctx: EngineerDep, session: SessionDep
) -> ExperimentRequestDetail:
    r = _request(session, ctx.org.id, request_id, decision=True)
    try:
        reject(session, ctx, r, body.spec_sha256, body.note)
    except SpecError as ex:
        raise _raise(ex) from ex
    audit_allow(session, ctx, "experiment.reject", f"experiment_request:{r.id}", sha256=r.spec_sha256)
    session.commit()
    return get_experiment_request(request_id, ctx, session)


@router.get("/experiment-trials/{trial_id}/artifacts/{name}")
def get_trial_artifact(
    trial_id: uuid.UUID, name: Annotated[str, Path(max_length=64)], ctx: ViewerDep, session: SessionDep,
    storage: StorageDep,
) -> Response:  # fmt: skip
    """The bytes of an artifact captured from a trial, as stored (checked against its digest when read)."""
    t = session.scalar(
        select(ExperimentTrial).where(ExperimentTrial.organization_id == ctx.org.id, ExperimentTrial.id == trial_id)
    )
    if t is None:
        raise error(404, "not_found", "trial not found")
    a = next((x for x in t.artifacts if x.get("name") == name and x.get("state") == "stored"), None)
    if a is None:
        raise error(404, "not_found", "no stored artifact of that name for this trial")
    return Response(
        storage.get(a["storage_key"]),
        media_type=a.get("media_type") or "application/octet-stream",
        headers={
            "X-Artifact-SHA256": a["sha256"],
            "Content-Disposition": f'attachment; filename="{a.get("filename") or name}"',
        },
    )


# ------------------------------------------------------------------------------- setups judged as releases (SIM-007)


class ReleaseEvaluationIn(BaseModel):
    version: int = Field(ge=1)
    baseline_arm: str = Field(min_length=1, max_length=64)
    candidate_arm: str = Field(min_length=1, max_length=64)
    project: str | None = Field(default=None, pattern=SLUG, description="Default: the project of the spec's model.")


class ReleaseEvaluationOut(BaseModel):
    """The engine's release verdict for two setups of one version, over every finished trial of its approved runs."""

    id: uuid.UUID
    version: int
    baseline_arm: str
    candidate_arm: str
    project: str
    evaluation_id: uuid.UUID
    state: str
    trials: dict[str, int]
    verdict: dict[str, Any] | None
    created_by: str
    created_at: datetime


def _release_eval_out(session: Session, ev: ExperimentEvaluation) -> ReleaseEvaluationOut:
    from ..evaluations.models import EvaluationJob
    from ..projects.models import Project

    job = session.get(EvaluationJob, ev.evaluation_id)
    v = session.get(ExperimentVersion, ev.version_id)
    p = session.get(Project, ev.project_id)
    assert job is not None and v is not None and p is not None
    return ReleaseEvaluationOut(
        id=ev.id,
        version=v.number,
        baseline_arm=ev.baseline_arm,
        candidate_arm=ev.candidate_arm,
        project=p.slug,
        evaluation_id=job.id,
        state=job.state,
        trials=ev.trials,
        verdict=verdict_of(session, job),
        created_by=ev.created_by,
        created_at=ev.created_at,
    )


@router.post(
    "/experiments/{experiment_slug}/release-evaluations",
    status_code=201,
    responses={200: {"description": "these trials were already judged: the same evaluation"}},
)
def judge_experiment_setups(
    experiment_slug: Annotated[str, Path(pattern=SLUG)],
    body: ReleaseEvaluationIn,
    ctx: EngineerDep,
    session: SessionDep,
    storage: StorageDep,
    response: Response,
) -> ReleaseEvaluationOut:
    """Judge a baseline and a candidate setup as releases with the engine's comparison (queued for the worker)."""
    e = _experiment(session, ctx.org.id, experiment_slug)
    v = _version(session, e, body.version)
    try:
        job, _, counts = judge_as_releases(
            session, get_settings(), storage, ctx, e, v, body.baseline_arm, body.candidate_arm, body.project
        )
    except SpecError as ex:
        session.rollback()
        raise _raise(ex) from ex
    same = session.scalar(
        select(ExperimentEvaluation).where(
            ExperimentEvaluation.experiment_id == e.id, ExperimentEvaluation.evaluation_id == job.id
        )
    )
    if same is not None:  # the same trials judged again: the same content-addressed evaluation
        session.commit()
        response.status_code = 200
        return _release_eval_out(session, same)
    ev = ExperimentEvaluation(
        experiment_id=e.id,
        organization_id=ctx.org.id,
        version_id=v.id,
        project_id=job.project_id,
        evaluation_id=job.id,
        baseline_arm=body.baseline_arm,
        candidate_arm=body.candidate_arm,
        trials=counts,
        created_by=ctx.principal.label,
    )
    session.add(ev)
    session.flush()
    audit_allow(session, ctx, "experiment.judge", f"experiment:{e.id}", evaluation=str(job.id), trials=counts)
    session.commit()
    return _release_eval_out(session, ev)


@router.get("/experiments/{experiment_slug}/release-evaluations")
def list_experiment_release_evaluations(
    experiment_slug: Annotated[str, Path(pattern=SLUG)], ctx: ViewerDep, session: SessionDep
) -> list[ReleaseEvaluationOut]:
    e = _experiment(session, ctx.org.id, experiment_slug)
    rows = session.scalars(
        select(ExperimentEvaluation)
        .where(ExperimentEvaluation.experiment_id == e.id)
        .order_by(ExperimentEvaluation.created_at.desc())
    ).all()
    return [_release_eval_out(session, ev) for ev in rows]
