"""Evaluation jobs: submission (idempotent), claiming with a lease, recovery, and persistence of results.

Queue = the ``evaluation_jobs`` table (decision D-005). A worker claims the oldest queued job with
``FOR UPDATE SKIP LOCKED``, holds a lease it renews by heartbeat, and may only write results while it still holds
the lease. A job whose lease expired (its worker died) is re-queued, or failed when its attempts are used up.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from openmhs_bridge import digest, sha256_text
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from ..contracts.episode import EvaluationConfig
from ..contracts.mapping import MappingSpec
from ..db import utcnow
from ..evidence.models import Artifact
from ..evidence.storage import Storage
from ..ingestion.models import MappingRevision
from ..organizations.models import Organization
from ..projects.models import Project
from ..releases.models import Release
from .models import EpisodeRecord, EvaluationJob, EvaluationResult, JobArtifact
from .pipeline import ArtifactInput, PipelineInput, PipelineOutput, ReleaseInput


class SubmissionError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def input_sha256(
    project: Project,
    baseline: Release,
    candidate: Release,
    mapping: MappingRevision,
    artifacts: dict[str, list[str]],
    config: EvaluationConfig,
    engine_sha256: str,
) -> str:
    """The idempotency key: everything the result depends on, and nothing else."""
    return digest(
        {
            "project": str(project.id),
            "baseline": [baseline.label, baseline.manifest_digest],
            "candidate": [candidate.label, candidate.manifest_digest],
            "mapping": mapping.spec_sha256,
            "artifacts": {k: sorted(v) for k, v in artifacts.items()},
            "config": config.model_dump(mode="json", by_alias=True),
            "engine": engine_sha256,
        }
    )


def _scoped(session: Session, model: Any, project: Project, ids: list[uuid.UUID]) -> list[Any]:
    rows = list(session.scalars(select(model).where(model.id.in_(ids), model.project_id == project.id)))
    if len(rows) != len(set(ids)):
        raise SubmissionError(404, "not_found", f"{model.__tablename__}: one or more ids not found in this project")
    return rows


def submit(
    session: Session,
    project: Project,
    *,
    baseline_release_id: uuid.UUID,
    candidate_release_id: uuid.UUID,
    mapping_id: uuid.UUID,
    baseline_artifact_ids: list[uuid.UUID],
    candidate_artifact_ids: list[uuid.UUID],
    config: EvaluationConfig,
    engine_sha256: str,
    actor: str,
    max_attempts: int,
) -> tuple[EvaluationJob, bool]:
    if baseline_release_id == candidate_release_id:
        raise SubmissionError(422, "input.same_release", "baseline and candidate must be different releases")
    if not baseline_artifact_ids or not candidate_artifact_ids:
        raise SubmissionError(422, "input.no_evidence", "each release needs at least one artifact")
    (baseline,) = _scoped(session, Release, project, [baseline_release_id])
    (candidate,) = _scoped(session, Release, project, [candidate_release_id])
    (mapping,) = _scoped(session, MappingRevision, project, [mapping_id])
    base_arts = _scoped(session, Artifact, project, baseline_artifact_ids)
    cand_arts = _scoped(session, Artifact, project, candidate_artifact_ids)
    if any(a.kind != "source" for a in base_arts + cand_arts):
        raise SubmissionError(422, "input.artifact_kind", "only uploaded source artifacts can be evaluated")
    key = input_sha256(
        project,
        baseline,
        candidate,
        mapping,
        {"baseline": [a.sha256 for a in base_arts], "candidate": [a.sha256 for a in cand_arts]},
        config,
        engine_sha256,
    )
    existing = session.scalar(
        select(EvaluationJob).where(EvaluationJob.project_id == project.id, EvaluationJob.input_sha256 == key)
    )
    if existing is not None:
        return existing, False
    job = EvaluationJob(
        project_id=project.id,
        baseline_release_id=baseline.id,
        candidate_release_id=candidate.id,
        mapping_id=mapping.id,
        config=config.model_dump(mode="json", by_alias=True),
        input_sha256=key,
        engine_sha256=engine_sha256,
        state="queued",
        attempts=0,
        max_attempts=max_attempts,
        created_by=actor,
    )
    session.add(job)
    session.flush()
    for rel, arts in ((baseline, base_arts), (candidate, cand_arts)):
        for a in arts:
            session.add(JobArtifact(job_id=job.id, artifact_id=a.id, release_id=rel.id))
    return job, True


# ------------------------------------------------------------------------------------------------ worker side


def claim(session: Session, worker: str, lease_s: int) -> uuid.UUID | None:
    row = session.execute(
        text(
            """
            UPDATE evaluation_jobs
               SET state = 'running', lease_owner = :worker, lease_expires_at = now() + make_interval(secs => :lease),
                   attempts = attempts + 1, started_at = coalesce(started_at, now()), updated_at = now(), error = NULL
             WHERE id = (SELECT id FROM evaluation_jobs
                          WHERE state = 'queued' AND NOT cancel_requested
                          ORDER BY created_at
                          FOR UPDATE SKIP LOCKED
                          LIMIT 1)
            RETURNING id
            """
        ),
        {"worker": worker, "lease": lease_s},
    ).first()
    session.commit()
    return row[0] if row else None


def heartbeat(session: Session, job_id: uuid.UUID, worker: str, lease_s: int) -> tuple[bool, bool]:
    """Extend the lease. Returns (still the owner, cancellation requested)."""
    row = session.execute(
        text(
            """
            UPDATE evaluation_jobs SET lease_expires_at = now() + make_interval(secs => :lease), updated_at = now()
             WHERE id = :id AND state = 'running' AND lease_owner = :worker
            RETURNING cancel_requested
            """
        ),
        {"id": job_id, "worker": worker, "lease": lease_s},
    ).first()
    session.commit()
    return (row is not None, bool(row[0]) if row else False)


def recover_expired(session: Session) -> int:
    """Jobs whose worker stopped renewing its lease: back to the queue, or failed when out of attempts."""
    rows = session.execute(
        text(
            """
            UPDATE evaluation_jobs
               SET state = CASE WHEN cancel_requested THEN 'cancelled'
                                WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
                   finished_at = CASE WHEN cancel_requested OR attempts >= max_attempts THEN now() END,
                   error = CASE WHEN cancel_requested THEN NULL
                                ELSE jsonb_build_object('code', 'worker.lost', 'transient', true,
                                     'message', 'the worker stopped renewing its lease', 'detail',
                                     jsonb_build_object('worker', lease_owner, 'attempt', attempts)) END,
                   lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
             WHERE state = 'running' AND lease_expires_at < now()
            RETURNING id
            """
        )
    ).all()
    session.commit()
    return len(rows)


def finish(session: Session, job_id: uuid.UUID, worker: str, state: str, error: dict[str, Any] | None = None) -> bool:
    res = session.execute(
        update(EvaluationJob)
        .where(EvaluationJob.id == job_id, EvaluationJob.lease_owner == worker, EvaluationJob.state == "running")
        .values(state=state, error=error, finished_at=utcnow(), lease_owner=None, lease_expires_at=None)
    )
    session.commit()
    return bool(getattr(res, "rowcount", 0) == 1)


def load_input(session: Session, job: EvaluationJob, storage: Storage) -> PipelineInput:
    project = session.get(Project, job.project_id)
    assert project is not None
    org = session.get(Organization, project.organization_id)
    assert org is not None
    mapping = session.get(MappingRevision, job.mapping_id)
    assert mapping is not None
    releases: dict[uuid.UUID, ReleaseInput] = {}
    for rel_id in (job.baseline_release_id, job.candidate_release_id):
        rel = session.get(Release, rel_id)
        assert rel is not None
        arts = session.scalars(
            select(Artifact)
            .join(JobArtifact, JobArtifact.artifact_id == Artifact.id)
            .where(JobArtifact.job_id == job.id, JobArtifact.release_id == rel_id)
            .order_by(Artifact.sha256)
        ).all()
        inputs = tuple(ArtifactInput(a.sha256, storage.get(a.storage_key), a.filename) for a in arts)
        releases[rel_id] = ReleaseInput(rel.label, rel.manifest, inputs)
    return PipelineInput(
        organization=org.slug,
        project=project.slug,
        baseline=releases[job.baseline_release_id],
        candidate=releases[job.candidate_release_id],
        mapping=MappingSpec.model_validate(mapping.spec),
        mapping_ref=mapping.ref,
        config=EvaluationConfig.model_validate(job.config),
    )


def _store_file(session: Session, storage: Storage, project_id: uuid.UUID, path: Path, kind: str, mt: str) -> str:
    def chunks() -> Any:
        with open(path, "rb") as f:
            while block := f.read(1 << 20):
                yield block

    stored = storage.put(chunks(), max_bytes=2 * 1024**3)
    existing = session.scalar(
        select(Artifact).where(Artifact.project_id == project_id, Artifact.sha256 == stored.sha256)
    )
    if existing is None:
        session.add(
            Artifact(
                project_id=project_id,
                sha256=stored.sha256,
                size_bytes=stored.size,
                media_type=mt,
                filename=path.name,
                storage_key=stored.key,
                kind=kind,
                created_by="worker",
            )
        )
    return stored.sha256


def persist_success(session: Session, job_id: uuid.UUID, worker: str, out: PipelineOutput, storage: Storage) -> bool:
    """Write everything in one transaction, only if this worker still holds the lease and nobody cancelled the job
    (the row is locked, so a cancellation cannot slip in between this check and the write)."""
    job = session.scalar(select(EvaluationJob).where(EvaluationJob.id == job_id).with_for_update())
    if job is None or job.lease_owner != worker or job.state != "running" or job.cancel_requested:
        session.rollback()
        return False
    rel_ids = {
        r.label: r.id
        for r in session.scalars(
            select(Release).where(Release.id.in_([job.baseline_release_id, job.candidate_release_id]))
        )
    }
    art_ids = {a.sha256: a.id for a in session.scalars(select(Artifact).where(Artifact.project_id == job.project_id))}
    for e in out.episodes:
        ep = e.mapped.episode
        report = dict(e.report) if e.report else None
        if report:
            report.pop("_conditions", None)
        session.add(
            EpisodeRecord(
                job_id=job.id,
                project_id=job.project_id,
                release_id=rel_ids[ep.release],
                artifact_id=art_ids[ep.source.artifact_sha256],
                episode_key=ep.episode_key,
                source_row=ep.source.row,
                robot=ep.robot,
                site=ep.site.value,
                scenario=ep.scenario.value,
                task_type=ep.task_type,
                ended_at=ep.ended_at,
                reported=ep.reported,
                verdict=e.verdict,
                outcome_class=e.outcome_class,
                reasons=e.reasons,
                document=ep.model_dump(mode="json", by_alias=True),
                verifier_report=report,
            )
        )
    outputs = {
        "validation": json.dumps(out.validation, sort_keys=True),
        "ingest": json.dumps(out.ingest, sort_keys=True),
        "compare_reported": out.reported_raw,
        "compare_verified": out.verified_raw,
        "compare_paired": out.paired_raw,
        "incidents": out.incidents_raw,
    }
    for kind, raw in outputs.items():
        if raw is not None:
            session.add(
                EvaluationResult(
                    job_id=job.id, kind=kind, payload=json.loads(raw), raw=raw, raw_sha256=sha256_text(raw)
                )
            )
    events_sha = _store_file(session, storage, job.project_id, out.events_path, "events", "application/x-ndjson")
    store_sha = _store_file(session, storage, job.project_id, out.store_path, "engine_store", "application/x-sqlite3")
    classes: dict[str, dict[str, int]] = {}
    for e in out.episodes:
        c = classes.setdefault(e.mapped.episode.release, {})
        c[e.outcome_class] = c.get(e.outcome_class, 0) + 1
    job.summary = {
        "episodes": len(out.episodes),
        "classes": classes,
        "verdict_reported": out.reported.verdict,
        "verdict_verified": out.verified.verdict if out.verified else None,
        "rejected_rows": sum(a["rejected"] for a in out.validation["artifacts"]),
    }
    job.provenance = {
        "engine": out.provenance.model_dump(mode="json"),
        "rules_version": out.reported.rules_version,
        "mapping": out.episodes[0].mapped.episode.mapping if out.episodes else None,
        "evidence_class": sorted({e.mapped.episode.evidence_class for e in out.episodes}),
        "inputs": {
            label: sorted(a["artifact"] for a in out.validation["artifacts"] if a["release"] == label)
            for label in {a["release"] for a in out.validation["artifacts"]}
        },
        "bundle": {"events": events_sha, "engine_store": store_sha},
        "input_sha256": job.input_sha256,
    }
    job.state = "succeeded"
    job.finished_at = utcnow()
    job.lease_owner = None
    job.lease_expires_at = None
    session.commit()
    return True


def lease_delta(lease_s: int) -> timedelta:
    return timedelta(seconds=lease_s)
