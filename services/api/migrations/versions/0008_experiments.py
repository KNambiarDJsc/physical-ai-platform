"""experiments: immutable versions, requests and approval, trials; recordings link to a workflow run

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-22 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
REQUEST_STATES = "state IN ('awaiting_approval', 'approved', 'rejected')"
CAPTURE_STATES = "capture_state IN ('none', 'pending', 'stored', 'failed')"


def _org_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=op.f(f"fk_{table}_organization_id_organizations"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(300), nullable=False),
        _org_fk("experiments"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiments")),
        sa.UniqueConstraint("organization_id", "slug", name=op.f("uq_experiments_organization_id_slug")),
    )
    op.create_index(op.f("ix_experiments_organization_id"), "experiments", ["organization_id"])

    op.create_table(
        "experiment_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("spec", JSONB, nullable=False),
        sa.Column("spec_sha256", sa.String(71), nullable=False),
        sa.Column("scenario", JSONB, nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(300), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_experiment_versions_experiment_id_experiments"),
            ondelete="CASCADE",
        ),
        _org_fk("experiment_versions"),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_experiment_versions_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment_versions")),
        sa.UniqueConstraint("experiment_id", "number", name=op.f("uq_experiment_versions_experiment_id_number")),
        sa.UniqueConstraint(
            "experiment_id", "spec_sha256", name=op.f("uq_experiment_versions_experiment_id_spec_sha256")
        ),
    )
    op.create_index(op.f("ix_experiment_versions_experiment_id"), "experiment_versions", ["experiment_id"])
    op.create_index(op.f("ix_experiment_versions_organization_id"), "experiment_versions", ["organization_id"])

    op.create_table(
        "experiment_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("spec_sha256", sa.String(71), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("requested_by", sa.String(300), nullable=False),
        sa.Column("requested_by_id", sa.String(300), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.String(300), nullable=True),
        sa.Column("decided_at", TZ, nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=False),
        sa.CheckConstraint(REQUEST_STATES, name=op.f("ck_experiment_requests_state")),
        _org_fk("experiment_requests"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["experiment_versions.id"],
            name=op.f("fk_experiment_requests_version_id_experiment_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment_requests")),
    )
    op.create_index(op.f("ix_experiment_requests_organization_id"), "experiment_requests", ["organization_id"])
    op.create_index(op.f("ix_experiment_requests_version_id"), "experiment_requests", ["version_id"])
    op.create_index(op.f("ix_experiment_requests_state"), "experiment_requests", ["state"])

    op.create_table(
        "experiment_trials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("arm", sa.String(64), nullable=False),
        sa.Column("repetition", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("capture_state", sa.String(16), nullable=False),
        sa.Column("artifacts", JSONB, nullable=False),
        sa.Column("capture_error", sa.Text(), nullable=True),
        sa.Column("recording_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(CAPTURE_STATES, name=op.f("ck_experiment_trials_capture_state")),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["experiment_requests.id"],
            name=op.f("fk_experiment_trials_request_id_experiment_requests"),
            ondelete="CASCADE",
        ),
        _org_fk("experiment_trials"),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            name=op.f("fk_experiment_trials_workflow_id_workflows"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_experiment_trials_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            name=op.f("fk_experiment_trials_recording_id_recordings"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment_trials")),
        sa.UniqueConstraint("run_id", name=op.f("uq_experiment_trials_run_id")),
        sa.UniqueConstraint(
            "request_id", "arm", "repetition", name=op.f("uq_experiment_trials_request_id_arm_repetition")
        ),
    )
    op.create_index(op.f("ix_experiment_trials_request_id"), "experiment_trials", ["request_id"])
    op.create_index(op.f("ix_experiment_trials_organization_id"), "experiment_trials", ["organization_id"])
    op.create_index(op.f("ix_experiment_trials_capture_state"), "experiment_trials", ["capture_state"])

    op.add_column("recordings", sa.Column("workflow_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_recordings_workflow_run_id_workflow_runs"),
        "recordings",
        "workflow_runs",
        ["workflow_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_recordings_workflow_run_id"), "recordings", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_recordings_workflow_run_id"), table_name="recordings")
    op.drop_constraint(op.f("fk_recordings_workflow_run_id_workflow_runs"), "recordings", type_="foreignkey")
    op.drop_column("recordings", "workflow_run_id")
    op.drop_table("experiment_trials")
    op.drop_table("experiment_requests")
    op.drop_table("experiment_versions")
    op.drop_table("experiments")
