"""hardware hub: environments, devices, capabilities

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21 16:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "environments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("adapter", sa.String(32), nullable=False),
        sa.Column("config_key", sa.String(64), nullable=False),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('simulated', 'physical')", name=op.f("ck_environments_kind")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_environments_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_environments")),
        sa.UniqueConstraint("organization_id", "slug", name=op.f("uq_environments_organization_id_slug")),
    )
    op.create_index(op.f("ix_environments_organization_id"), "environments", ["organization_id"])
    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("protocol", sa.String(32), nullable=False),
        sa.Column("td_sha256", sa.String(64), nullable=False),
        sa.Column("declares_simulated", sa.Boolean(), nullable=False),
        sa.Column("description_document", JSONB, nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_devices_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_devices_environment_id_environments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
        sa.UniqueConstraint("environment_id", "key", name=op.f("uq_devices_environment_id_key")),
    )
    op.create_index(op.f("ix_devices_organization_id"), "devices", ["organization_id"])
    op.create_index(op.f("ix_devices_environment_id"), "devices", ["environment_id"])
    op.create_table(
        "device_capabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("read_only", sa.Boolean(), nullable=False),
        sa.Column("data_schema", JSONB, nullable=False),
        sa.Column("input_schema", JSONB, nullable=True),
        sa.Column("output_schema", JSONB, nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.CheckConstraint("kind IN ('property', 'action')", name=op.f("ck_device_capabilities_kind")),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name=op.f("fk_device_capabilities_device_id_devices"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_capabilities")),
        sa.UniqueConstraint("device_id", "kind", "name", name=op.f("uq_device_capabilities_device_id_kind_name")),
    )
    op.create_index(op.f("ix_device_capabilities_device_id"), "device_capabilities", ["device_id"])


def downgrade() -> None:
    op.drop_table("device_capabilities")
    op.drop_table("devices")
    op.drop_table("environments")
