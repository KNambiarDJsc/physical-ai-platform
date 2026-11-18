from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, CreatedMixin, IdMixin


class Release(IdMixin, CreatedMixin, Base):
    """A software or policy release: an OpenMHS deployment manifest whose labels.release is ``label``."""

    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("project_id", "label"),
        CheckConstraint("kind IN ('software', 'policy')", name="kind"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(String(2000))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    manifest_digest: Mapped[str] = mapped_column(String(71))
    created_by: Mapped[str] = mapped_column(String(300))
