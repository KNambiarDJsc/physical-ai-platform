"""workflows, workflow runs, step journal

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-21 17:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
TZ = sa.DateTime(timezone=True)
RUN_STATES = "state IN ('queued', 'running', 'succeeded', 'failed', 'outcome_unknown', 'cancelled')"
STEP_STATES = "state IN ('pending', 'dispatching', 'completed', 'failed', 'refused', 'outcome_unknown')"


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("template", sa.String(64), nullable=True),
        sa.Column("parameters", JSONB, nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("definition_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_workflows_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_workflows_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflows")),
        sa.UniqueConstraint("organization_id", "slug", name=op.f("uq_workflows_organization_id_slug")),
    )
    op.create_index(op.f("ix_workflows_organization_id"), "workflows", ["organization_id"])
    op.create_index(op.f("ix_workflows_environment_id"), "workflows", ["environment_id"])
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(200), nullable=True),
        sa.Column("lease_expires_at", TZ, nullable=True),
        sa.Column("submitted_by", sa.String(300), nullable=False),
        sa.Column("reported", JSONB, nullable=True),
        sa.Column("verification", JSONB, nullable=True),
        sa.Column("outcome_class", sa.String(32), nullable=True),
        sa.Column("provenance", JSONB, nullable=True),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("started_at", TZ, nullable=True),
        sa.Column("finished_at", TZ, nullable=True),
        sa.Column("updated_at", TZ, nullable=False),
        sa.CheckConstraint(RUN_STATES, name=op.f("ck_workflow_runs_state")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_workflow_runs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["workflows.id"], name=op.f("fk_workflow_runs_workflow_id_workflows"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_workflow_runs_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    op.create_index(op.f("ix_workflow_runs_organization_id"), "workflow_runs", ["organization_id"])
    op.create_index(op.f("ix_workflow_runs_workflow_id"), "workflow_runs", ["workflow_id"])
    op.create_index(op.f("ix_workflow_runs_state"), "workflow_runs", ["state"])
    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("device_key", sa.String(128), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("input", JSONB, nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("idempotent", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("dispatches", sa.Integer(), nullable=False),
        sa.Column("output", JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("invocation_id", sa.String(64), nullable=True),
        sa.Column("started_at", TZ, nullable=True),
        sa.Column("finished_at", TZ, nullable=True),
        sa.CheckConstraint(STEP_STATES, name=op.f("ck_workflow_steps_state")),
        sa.ForeignKeyConstraint(
            ["run_id"], ["workflow_runs.id"], name=op.f("fk_workflow_steps_run_id_workflow_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name=op.f("fk_workflow_steps_device_id_devices"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_steps")),
        sa.UniqueConstraint("run_id", "position", name=op.f("uq_workflow_steps_run_id_position")),
    )
    op.create_index(op.f("ix_workflow_steps_run_id"), "workflow_steps", ["run_id"])


def downgrade() -> None:
    op.drop_table("workflow_steps")
    op.drop_table("workflow_runs")
    op.drop_table("workflows")
