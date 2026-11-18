from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, CreatedMixin, IdMixin


class Artifact(IdMixin, CreatedMixin, Base):
    """A stored source file. Identity is its content (sha256) within a project; bytes never change."""

    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("project_id", "sha256"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    sha256: Mapped[str] = mapped_column(String(71))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(200), doc="Display only; never used as a path")
    storage_key: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32), default="source", doc="source | events | engine_store")
    created_by: Mapped[str] = mapped_column(String(300))
