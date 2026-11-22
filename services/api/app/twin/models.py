from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, CreatedMixin, IdMixin


class RobotModel(IdMixin, CreatedMixin, Base):
    """A named robot model in a project; its content lives in immutable numbered versions."""

    __tablename__ = "robot_models"
    __table_args__ = (UniqueConstraint("project_id", "slug"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(63))
    name: Mapped[str] = mapped_column(String(200))


class RobotModelVersion(IdMixin, CreatedMixin, Base):
    """One URDF plus the files it references. Immutable: a change is a new version (a different manifest digest)."""

    __tablename__ = "robot_model_versions"
    __table_args__ = (UniqueConstraint("model_id", "number"), UniqueConstraint("model_id", "manifest_sha256"))

    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("robot_models.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    manifest_sha256: Mapped[str] = mapped_column(String(71))
    urdf_path: Mapped[str] = mapped_column(String(200))
    source: Mapped[dict[str, Any]] = mapped_column(JSONB, doc="repository, commit, licence, notice: as declared")
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, doc="path, sha256, size_bytes, media_type, storage_key")
    omitted: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, doc="upstream files not stored, each with its reason")
    structure: Mapped[dict[str, Any]] = mapped_column(
        JSONB, doc="links, joints, controllers, sensors read from the URDF"
    )
    created_by: Mapped[str] = mapped_column(String(300))


class Recording(IdMixin, CreatedMixin, Base):
    """An MCAP recording with the track decoded from it. The bytes are in content-addressed storage."""

    __tablename__ = "recordings"
    __table_args__ = (UniqueConstraint("project_id", "sha256"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(71))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(200))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, doc="the observer's bag summary, as uploaded")
    identity: Mapped[dict[str, Any] | None] = mapped_column(JSONB, doc="the run identity, as uploaded and as reported")
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("robot_model_versions.id", ondelete="SET NULL"), nullable=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    track: Mapped[dict[str, Any]] = mapped_column(JSONB)
    track_sha256: Mapped[str] = mapped_column(String(71))
    created_by: Mapped[str] = mapped_column(String(300))
