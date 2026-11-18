"""Audit log of protected actions and authorization decisions. Append-only from the application's side."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base, utcnow


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # NULL when the caller has no access to the organization they named (the attempt is still recorded).
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    actor: Mapped[str] = mapped_column(String(300))
    action: Mapped[str] = mapped_column(String(100))
    resource: Mapped[str] = mapped_column(String(300))
    decision: Mapped[str] = mapped_column(String(8))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


def record(
    session: Session,
    *,
    actor: str,
    action: str,
    resource: str,
    decision: str,
    organization_id: uuid.UUID | None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Add an audit row to the session. Denials are committed by the caller's error path (see auth.deps)."""
    if decision not in ("allow", "deny"):
        raise ValueError(decision)
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor=actor,
            action=action,
            resource=resource,
            decision=decision,
            detail=detail or {},
        )
    )
