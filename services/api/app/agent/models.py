"""Experiment proposals: what an engineering assistant (or anyone) suggests running, awaiting a person's decision."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, CreatedMixin, IdMixin

PROPOSAL_STATES = ("proposed", "approved", "rejected")


class ExperimentProposal(IdMixin, CreatedMixin, Base):
    __tablename__ = "experiment_proposals"
    __table_args__ = (CheckConstraint(f"state IN {PROPOSAL_STATES}", name="state"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[Any]] = mapped_column(
        JSONB, default=list
    )  # ids the proposer cites (runs, steps, digests)
    state: Mapped[str] = mapped_column(String(12), default="proposed", index=True)
    proposed_by: Mapped[str] = mapped_column(String(300))
    channel: Mapped[str] = mapped_column(String(32), default="api")  # "agent-tools" when it came through the tool layer
    decided_by: Mapped[str | None] = mapped_column(String(300))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_runs.id", ondelete="SET NULL"))
