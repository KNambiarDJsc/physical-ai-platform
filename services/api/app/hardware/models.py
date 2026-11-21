"""Hardware Hub: execution environments, the devices discovered in them, and each device's capabilities."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, CreatedMixin, IdMixin, utcnow


class Environment(IdMixin, CreatedMixin, Base):
    """A workspace's connection to one operator-configured environment (``PAP_ENVIRONMENTS`` entry ``config_key``)."""

    __tablename__ = "environments"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug"),
        CheckConstraint("kind IN ('simulated', 'physical')", name="kind"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))
    adapter: Mapped[str] = mapped_column(String(32))
    config_key: Mapped[str] = mapped_column(String(64))
    last_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(IdMixin, CreatedMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("environment_id", "key"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    protocol: Mapped[str] = mapped_column(String(32))
    td_sha256: Mapped[str] = mapped_column(String(64))
    declares_simulated: Mapped[bool] = mapped_column(Boolean)
    description_document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Capability(IdMixin, Base):
    __tablename__ = "device_capabilities"
    __table_args__ = (
        UniqueConstraint("device_id", "kind", "name"),
        CheckConstraint("kind IN ('property', 'action')", name="kind"),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    read_only: Mapped[bool] = mapped_column(Boolean)
    data_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    input_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
