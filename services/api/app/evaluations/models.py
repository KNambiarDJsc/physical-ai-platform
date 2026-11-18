from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, CreatedMixin, IdMixin, utcnow

STATES = ("queued", "running", "succeeded", "failed", "cancelled")


class EvaluationJob(IdMixin, CreatedMixin, Base):
    __tablename__ = "evaluation_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "input_sha256"),
        CheckConstraint("state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="state"),
        CheckConstraint("baseline_release_id <> candidate_release_id", name="distinct_releases"),
        Index("ix_evaluation_jobs_claim", "state", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    baseline_release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id", ondelete="RESTRICT"))
    candidate_release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id", ondelete="RESTRICT"))
    mapping_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mapping_revisions.id", ondelete="RESTRICT"))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    input_sha256: Mapped[str] = mapped_column(String(71))
    engine_sha256: Mapped[str] = mapped_column(String(71))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    timeout_s: Mapped[int] = mapped_column(Integer, default=1800)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(String(300))


class JobArtifact(Base):
    """Which stored artifacts are evidence for which release in a job."""

    __tablename__ = "job_artifacts"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_jobs.id", ondelete="CASCADE"), primary_key=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id", ondelete="RESTRICT"), primary_key=True)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id", ondelete="RESTRICT"), primary_key=True)


class EvaluationResult(CreatedMixin, Base):
    """An engine output, verbatim (``payload``), with the digest of its exact bytes."""

    __tablename__ = "evaluation_results"
    __table_args__ = (UniqueConstraint("job_id", "kind"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[Any] = mapped_column(JSONB)
    raw: Mapped[str] = mapped_column(Text, doc="The engine's output, byte for byte")
    raw_sha256: Mapped[str] = mapped_column(String(71))


class EpisodeRecord(IdMixin, Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("job_id", "release_id", "episode_key"),
        Index("ix_episodes_job_class", "job_id", "outcome_class"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_jobs.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id", ondelete="RESTRICT"))
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id", ondelete="RESTRICT"))
    episode_key: Mapped[str] = mapped_column(String(200))
    source_row: Mapped[int] = mapped_column(Integer)
    robot: Mapped[str] = mapped_column(String(200))
    site: Mapped[str | None] = mapped_column(String(200))
    scenario: Mapped[str | None] = mapped_column(String(200))
    task_type: Mapped[str] = mapped_column(String(200))
    ended_at: Mapped[str] = mapped_column(String(40))
    reported: Mapped[str] = mapped_column(String(16))
    verdict: Mapped[str | None] = mapped_column(String(16))
    outcome_class: Mapped[str] = mapped_column(String(32))
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    verifier_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
