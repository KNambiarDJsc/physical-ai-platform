"""digital twin: robot models, versions and recordings

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-22 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "robot_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_robot_models_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_robot_models")),
        sa.UniqueConstraint("project_id", "slug", name=op.f("uq_robot_models_project_id_slug")),
    )
    op.create_index(op.f("ix_robot_models_project_id"), "robot_models", ["project_id"])
    op.create_table(
        "robot_model_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("manifest_sha256", sa.String(71), nullable=False),
        sa.Column("urdf_path", sa.String(200), nullable=False),
        sa.Column("source", JSONB, nullable=False),
        sa.Column("files", JSONB, nullable=False),
        sa.Column("omitted", JSONB, nullable=False),
        sa.Column("structure", JSONB, nullable=False),
        sa.Column("created_by", sa.String(300), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["robot_models.id"],
            name=op.f("fk_robot_model_versions_model_id_robot_models"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_robot_model_versions_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_robot_model_versions")),
        sa.UniqueConstraint("model_id", "number", name=op.f("uq_robot_model_versions_model_id_number")),
        sa.UniqueConstraint(
            "model_id", "manifest_sha256", name=op.f("uq_robot_model_versions_model_id_manifest_sha256")
        ),
    )
    op.create_index(op.f("ix_robot_model_versions_model_id"), "robot_model_versions", ["model_id"])
    op.create_index(op.f("ix_robot_model_versions_project_id"), "robot_model_versions", ["project_id"])
    op.create_table(
        "recordings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("sha256", sa.String(71), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.Column("summary", JSONB, nullable=True),
        sa.Column("identity", JSONB, nullable=True),
        sa.Column("model_version_id", sa.Uuid(), nullable=True),
        sa.Column("episode_id", sa.Uuid(), nullable=True),
        sa.Column("track", JSONB, nullable=False),
        sa.Column("track_sha256", sa.String(71), nullable=False),
        sa.Column("created_by", sa.String(300), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_recordings_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["robot_model_versions.id"],
            name=op.f("fk_recordings_model_version_id_robot_model_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id"], ["episodes.id"], name=op.f("fk_recordings_episode_id_episodes"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recordings")),
        sa.UniqueConstraint("project_id", "sha256", name=op.f("uq_recordings_project_id_sha256")),
    )
    op.create_index(op.f("ix_recordings_project_id"), "recordings", ["project_id"])
    op.create_index(op.f("ix_recordings_episode_id"), "recordings", ["episode_id"])


def downgrade() -> None:
    op.drop_table("recordings")
    op.drop_table("robot_model_versions")
    op.drop_table("robot_models")
