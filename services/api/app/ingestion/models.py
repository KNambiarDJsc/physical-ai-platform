from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, CreatedMixin, IdMixin


class MappingRevision(IdMixin, CreatedMixin, Base):
    """One immutable version of a ``pap.mapping/1``. There is no update: a change is a new version."""

    __tablename__ = "mapping_revisions"
    __table_args__ = (UniqueConstraint("project_id", "name", "version"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec_sha256: Mapped[str] = mapped_column(String(71))
    created_by: Mapped[str] = mapped_column(String(300))

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version} {self.spec_sha256}"
