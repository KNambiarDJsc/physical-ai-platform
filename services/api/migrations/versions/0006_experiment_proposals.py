"""experiment proposals

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21 20:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "experiment_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("proposed_by", sa.String(300), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("decided_by", sa.String(300), nullable=True),
        sa.Column("decided_at", TZ, nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("state IN ('proposed', 'approved', 'rejected')", name=op.f("ck_experiment_proposals_state")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_experiment_proposals_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            name=op.f("fk_experiment_proposals_workflow_id_workflows"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_experiment_proposals_run_id_workflow_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment_proposals")),
    )
    op.create_index(op.f("ix_experiment_proposals_organization_id"), "experiment_proposals", ["organization_id"])
    op.create_index(op.f("ix_experiment_proposals_workflow_id"), "experiment_proposals", ["workflow_id"])
    op.create_index(op.f("ix_experiment_proposals_state"), "experiment_proposals", ["state"])


def downgrade() -> None:
    op.drop_table("experiment_proposals")
