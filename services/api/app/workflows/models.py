"""Workflows (ordered device actions plus a verification contract), their runs, and each run's step journal."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, CreatedMixin, IdMixin, utcnow

RUN_STATES = ("queued", "running", "succeeded", "failed", "outcome_unknown", "cancelled")
STEP_STATES = ("pending", "dispatching", "completed", "failed", "refused", "outcome_unknown")


class Workflow(IdMixin, CreatedMixin, Base):
    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    template: Mapped[str | None] = mapped_column(String(64))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    definition_sha256: Mapped[str] = mapped_column(String(64))


class WorkflowRun(IdMixin, CreatedMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (CheckConstraint(f"state IN {RUN_STATES}", name="state"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)  # snapshot: a run never changes with its workflow
    state: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[str] = mapped_column(String(300))
    reported: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # what the instrument reported
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # the engine's verifier report
    outcome_class: Mapped[str | None] = mapped_column(String(32))
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowStep(IdMixin, Base):
    """The journal: written as ``dispatching`` before a command leaves, and with the answer after (D-028)."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "position"),
        CheckConstraint(f"state IN {STEP_STATES}", name="state"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    step_key: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    device_key: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    request_id: Mapped[str] = mapped_column(String(64))
    idempotent: Mapped[bool] = mapped_column(default=False)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    dispatches: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[Any] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text)
    invocation_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
