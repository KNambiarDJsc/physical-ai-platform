"""experiment evaluations: two setups of a version judged as releases

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-22 22:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    t = "experiment_evaluations"
    op.create_table(
        t,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_arm", sa.String(64), nullable=False),
        sa.Column("candidate_arm", sa.String(64), nullable=False),
        sa.Column("trials", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(300), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.id"], name=op.f(f"fk_{t}_experiment_id_experiments"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f(f"fk_{t}_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["experiment_versions.id"],
            name=op.f(f"fk_{t}_version_id_experiment_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f(f"fk_{t}_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluation_jobs.id"],
            name=op.f(f"fk_{t}_evaluation_id_evaluation_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
    )
    op.create_index(op.f(f"ix_{t}_experiment_id"), t, ["experiment_id"])
    op.create_index(op.f(f"ix_{t}_organization_id"), t, ["organization_id"])


def downgrade() -> None:
    op.drop_table("experiment_evaluations")
