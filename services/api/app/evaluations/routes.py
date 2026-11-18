"""Release Intelligence API: submit evaluations, follow them, read comparisons and episodes.

The comparison endpoint returns the engine's outputs verbatim (``raw``) and parsed (``result``); nothing here
computes a statistic. Every response about results carries the job's provenance.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..auth.deps import ProjectEngineer, ProjectViewer, audit_allow, error
from ..config import Settings, get_settings
from ..contracts.episode import EvaluationConfig, OutcomeClass
from ..db import get_session, utcnow
from ..engine import get_engine
from ..releases.models import Release
from . import service
from .models import EpisodeRecord, EvaluationJob, EvaluationResult, JobArtifact

router = APIRouter(prefix="/api/v1/orgs/{org_slug}/projects/{project_slug}/evaluations", tags=["evaluations"])
SessionDep = Annotated[Session, Depends(get_session)]


class EvaluationIn(BaseModel):
    baseline_release_id: uuid.UUID
    candidate_release_id: uuid.UUID
    mapping_id: uuid.UUID
    baseline_artifact_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    candidate_artifact_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    config: EvaluationConfig


class EvaluationOut(BaseModel):
    id: uuid.UUID
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    baseline_release_id: uuid.UUID
    candidate_release_id: uuid.UUID
    baseline_label: str
    candidate_label: str
    mapping_id: uuid.UUID
    config: dict[str, Any]
    input_sha256: str
    attempts: int
    max_attempts: int
    cancel_requested: bool
    error: dict[str, Any] | None
    summary: dict[str, Any] | None
    provenance: dict[str, Any] | None
    artifacts: dict[str, list[uuid.UUID]]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_by: str


def _out(session: Session, job: EvaluationJob) -> EvaluationOut:
    labels: dict[uuid.UUID, str] = {
        rid: label
        for rid, label in session.execute(
            select(Release.id, Release.label).where(Release.id.in_([job.baseline_release_id, job.candidate_release_id]))
        )
    }
    arts: dict[str, list[uuid.UUID]] = {"baseline": [], "candidate": []}
    for art_id, rel_id in session.execute(
        select(JobArtifact.artifact_id, JobArtifact.release_id).where(JobArtifact.job_id == job.id)
    ):
        arts["baseline" if rel_id == job.baseline_release_id else "candidate"].append(art_id)
    return EvaluationOut(
        id=job.id,
        state=job.state,
        baseline_release_id=job.baseline_release_id,
        candidate_release_id=job.candidate_release_id,
        baseline_label=labels[job.baseline_release_id],
        candidate_label=labels[job.candidate_release_id],
        mapping_id=job.mapping_id,
        config=job.config,
        input_sha256=job.input_sha256,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        cancel_requested=job.cancel_requested,
        error=job.error,
        summary=job.summary,
        provenance=job.provenance,
        artifacts={k: sorted(v, key=str) for k, v in arts.items()},
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_by=job.created_by,
    )


def _job(session: Session, project_id: uuid.UUID, job_id: uuid.UUID) -> EvaluationJob:
    job = session.scalar(
        select(EvaluationJob).where(EvaluationJob.id == job_id, EvaluationJob.project_id == project_id)
    )
    if job is None:
        raise error(404, "not_found", "evaluation not found")
    return job


@router.post("", status_code=201, responses={200: {"description": "the same inputs were already submitted"}})
def submit(
    body: EvaluationIn,
    ctx: ProjectEngineer,
    session: SessionDep,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> EvaluationOut:
    try:
        engine_sha = get_engine().config.expected_sha256
        job, created = service.submit(
            session,
            ctx.project,
            baseline_release_id=body.baseline_release_id,
            candidate_release_id=body.candidate_release_id,
            mapping_id=body.mapping_id,
            baseline_artifact_ids=body.baseline_artifact_ids,
            candidate_artifact_ids=body.candidate_artifact_ids,
            config=body.config,
            engine_sha256=engine_sha,
            actor=ctx.principal.label,
            max_attempts=settings.job_max_attempts,
        )
    except service.SubmissionError as e:
        session.rollback()
        raise error(e.status, e.code, e.message) from e
    if created:
        audit_allow(session, ctx, "evaluation.submit", f"evaluation:{job.id}", input_sha256=job.input_sha256)
        session.commit()
    else:
        response.status_code = 200
    return _out(session, job)


@router.get("")
def list_evaluations(
    ctx: ProjectViewer, session: SessionDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[EvaluationOut]:
    rows = session.scalars(
        select(EvaluationJob)
        .where(EvaluationJob.project_id == ctx.project.id)
        .order_by(EvaluationJob.created_at.desc())
        .limit(limit)
    )
    return [_out(session, j) for j in rows]


@router.get("/{job_id}")
def get_evaluation(job_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> EvaluationOut:
    return _out(session, _job(session, ctx.project.id, job_id))


@router.post("/{job_id}/cancel")
def cancel(job_id: uuid.UUID, ctx: ProjectEngineer, session: SessionDep) -> EvaluationOut:
    job = _job(session, ctx.project.id, job_id)
    if job.state == "queued":
        session.execute(
            update(EvaluationJob)
            .where(EvaluationJob.id == job.id, EvaluationJob.state == "queued")
            .values(state="cancelled", cancel_requested=True, finished_at=utcnow())
        )
    elif job.state == "running":
        job.cancel_requested = True
    else:
        raise error(409, "conflict", f"the evaluation is already {job.state}")
    audit_allow(session, ctx, "evaluation.cancel", f"evaluation:{job.id}")
    session.commit()
    session.refresh(job)
    return _out(session, job)


def _results(session: Session, job: EvaluationJob) -> dict[str, EvaluationResult]:
    if job.state != "succeeded":
        raise error(409, "not_ready", f"the evaluation is {job.state}")
    return {r.kind: r for r in session.scalars(select(EvaluationResult).where(EvaluationResult.job_id == job.id))}


def _result_doc(r: EvaluationResult | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {"result": r.payload, "raw": r.raw, "raw_sha256": r.raw_sha256}


@router.get("/{job_id}/comparison")
def comparison(job_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> dict[str, Any]:
    """The engine's comparisons, unchanged, with the provenance of the run."""
    job = _job(session, ctx.project.id, job_id)
    res = _results(session, job)
    return {
        "evaluation": str(job.id),
        "reported": _result_doc(res.get("compare_reported")),
        "verified": _result_doc(res.get("compare_verified")),
        "paired": _result_doc(res.get("compare_paired")),
        "summary": job.summary,
        "provenance": job.provenance,
        "config": job.config,
    }


@router.get("/{job_id}/validation")
def validation(job_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> dict[str, Any]:
    job = _job(session, ctx.project.id, job_id)
    r = _results(session, job).get("validation")
    return r.payload if r else {}


@router.get("/{job_id}/incidents")
def incidents(job_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> Any:
    job = _job(session, ctx.project.id, job_id)
    r = _results(session, job).get("incidents")
    return r.payload if r else []


class EpisodeOut(BaseModel):
    id: uuid.UUID
    release_id: uuid.UUID
    episode_key: str
    robot: str
    site: str | None
    scenario: str | None
    task_type: str
    ended_at: str
    reported: str
    verdict: str | None
    outcome_class: str
    reasons: list[str]
    source_artifact_id: uuid.UUID
    source_row: int


class EpisodePage(BaseModel):
    total: int
    items: list[EpisodeOut]


class EpisodeDetail(EpisodeOut):
    document: dict[str, Any]
    verifier_report: dict[str, Any] | None


def _ep(e: EpisodeRecord) -> dict[str, Any]:
    return {
        "id": e.id,
        "release_id": e.release_id,
        "episode_key": e.episode_key,
        "robot": e.robot,
        "site": e.site,
        "scenario": e.scenario,
        "task_type": e.task_type,
        "ended_at": e.ended_at,
        "reported": e.reported,
        "verdict": e.verdict,
        "outcome_class": e.outcome_class,
        "reasons": e.reasons,
        "source_artifact_id": e.artifact_id,
        "source_row": e.source_row,
    }


@router.get("/{job_id}/episodes")
def episodes(
    job_id: uuid.UUID,
    ctx: ProjectViewer,
    session: SessionDep,
    release_id: uuid.UUID | None = None,
    outcome_class: OutcomeClass | None = None,
    verdict: Literal["satisfied", "violated", "unknown"] | None = None,
    scenario: Annotated[str | None, Query(max_length=200)] = None,
    site: Annotated[str | None, Query(max_length=200)] = None,
    robot: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EpisodePage:
    job = _job(session, ctx.project.id, job_id)
    q = select(EpisodeRecord).where(EpisodeRecord.job_id == job.id, EpisodeRecord.project_id == ctx.project.id)
    for col, val in (
        (EpisodeRecord.release_id, release_id),
        (EpisodeRecord.outcome_class, outcome_class),
        (EpisodeRecord.verdict, verdict),
        (EpisodeRecord.scenario, scenario),
        (EpisodeRecord.site, site),
        (EpisodeRecord.robot, robot),
    ):
        if val is not None:
            q = q.where(col == val)
    total = session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = session.scalars(q.order_by(EpisodeRecord.ended_at, EpisodeRecord.episode_key).limit(limit).offset(offset))
    return EpisodePage(total=total, items=[EpisodeOut(**_ep(e)) for e in rows])


@router.get("/{job_id}/episodes/{episode_id}")
def episode(job_id: uuid.UUID, episode_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> EpisodeDetail:
    job = _job(session, ctx.project.id, job_id)
    e = session.scalar(
        select(EpisodeRecord).where(
            EpisodeRecord.id == episode_id, EpisodeRecord.job_id == job.id, EpisodeRecord.project_id == ctx.project.id
        )
    )
    if e is None:
        raise error(404, "not_found", "episode not found")
    return EpisodeDetail(**_ep(e), document=e.document, verifier_report=e.verifier_report)
