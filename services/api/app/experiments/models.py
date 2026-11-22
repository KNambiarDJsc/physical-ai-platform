"""Experiments: a name, immutable versions (specs), requests to run a version, and the trials an approval queued."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, CreatedMixin, IdMixin

REQUEST_STATES = ("awaiting_approval", "approved", "rejected")
CAPTURE_STATES = ("none", "pending", "stored", "failed")


class Experiment(IdMixin, CreatedMixin, Base):
    __tablename__ = "experiments"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(300))


class ExperimentVersion(IdMixin, CreatedMixin, Base):
    """One immutable spec. Never updated: a change is a new version (a different checksum)."""

    __tablename__ = "experiment_versions"
    __table_args__ = (UniqueConstraint("experiment_id", "number"), UniqueConstraint("experiment_id", "spec_sha256"))

    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec_sha256: Mapped[str] = mapped_column(String(71))
    scenario: Mapped[dict[str, Any]] = mapped_column(JSONB, doc="the scenario as the host listed it at creation")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(300))


class ExperimentRequest(IdMixin, CreatedMixin, Base):
    """A request to run one version. Only an approval of this exact checksum queues anything."""

    __tablename__ = "experiment_requests"
    __table_args__ = (CheckConstraint(f"state IN {REQUEST_STATES}", name="state"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_versions.id", ondelete="CASCADE"), index=True)
    spec_sha256: Mapped[str] = mapped_column(String(71))
    state: Mapped[str] = mapped_column(String(24), default="awaiting_approval", index=True)
    requested_by: Mapped[str] = mapped_column(String(300))
    requested_by_id: Mapped[str] = mapped_column(String(300))
    note: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str | None] = mapped_column(String(300))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str] = mapped_column(Text, default="")


class ExperimentTrial(IdMixin, CreatedMixin, Base):
    """One trial: an ordinary workflow run, with the arm, repetition and seed it stands for, and what was captured."""

    __tablename__ = "experiment_trials"
    __table_args__ = (
        UniqueConstraint("request_id", "arm", "repetition"),
        CheckConstraint(f"capture_state IN {CAPTURE_STATES}", name="capture_state"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_requests.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    arm: Mapped[str] = mapped_column(String(64))
    repetition: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int | None] = mapped_column(Integer)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True)
    capture_state: Mapped[str] = mapped_column(String(16), default="none", index=True)
    artifacts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    capture_error: Mapped[str | None] = mapped_column(Text)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recordings.id", ondelete="SET NULL"), nullable=True
    )
