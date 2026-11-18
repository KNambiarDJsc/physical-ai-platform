"""Mapping revisions: create (a new version) and read. There is deliberately no update or delete."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from openmhs_bridge import digest
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import ProjectEngineer, ProjectViewer, audit_allow, error
from ..contracts.mapping import MappingSpec
from ..db import get_session
from .models import MappingRevision

router = APIRouter(prefix="/api/v1/orgs/{org_slug}/projects/{project_slug}/mappings", tags=["mappings"])
SessionDep = Annotated[Session, Depends(get_session)]


class MappingOut(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    spec_sha256: str
    spec: dict[str, Any]
    created_at: datetime
    created_by: str


def out(m: MappingRevision) -> MappingOut:
    return MappingOut(
        id=m.id,
        name=m.name,
        version=m.version,
        spec_sha256=m.spec_sha256,
        spec=m.spec,
        created_at=m.created_at,
        created_by=m.created_by,
    )


@router.post("", status_code=201, responses={200: {"description": "identical to the latest version"}})
def create_mapping(spec: MappingSpec, ctx: ProjectEngineer, session: SessionDep) -> Any:
    doc = spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    try:
        sha = digest(doc)
    except ValueError as e:
        raise error(422, "mapping.number", str(e)) from e
    latest = session.scalar(
        select(MappingRevision)
        .where(MappingRevision.project_id == ctx.project.id, MappingRevision.name == spec.name)
        .order_by(MappingRevision.version.desc())
        .limit(1)
    )
    if latest is not None and latest.spec_sha256 == sha:
        return JSONResponse(out(latest).model_dump(mode="json"), status_code=200)
    version = (
        session.scalar(
            select(func.max(MappingRevision.version)).where(
                MappingRevision.project_id == ctx.project.id, MappingRevision.name == spec.name
            )
        )
        or 0
    ) + 1
    m = MappingRevision(
        project_id=ctx.project.id,
        name=spec.name,
        version=version,
        spec=doc,
        spec_sha256=sha,
        created_by=ctx.principal.label,
    )
    session.add(m)
    try:
        session.flush()
    except IntegrityError as e:  # a concurrent writer took this version number
        session.rollback()
        raise error(409, "conflict", "another version was created at the same time; retry") from e
    audit_allow(session, ctx, "mapping.create", f"mapping:{m.id}", name=m.name, version=m.version)
    session.commit()
    return out(m)


@router.get("")
def list_mappings(ctx: ProjectViewer, session: SessionDep) -> list[MappingOut]:
    rows = session.scalars(
        select(MappingRevision)
        .where(MappingRevision.project_id == ctx.project.id)
        .order_by(MappingRevision.name, MappingRevision.version)
    )
    return [out(m) for m in rows]


@router.get("/{mapping_id}")
def get_mapping(mapping_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> MappingOut:
    m = session.scalar(
        select(MappingRevision).where(MappingRevision.id == mapping_id, MappingRevision.project_id == ctx.project.id)
    )
    if m is None:
        raise error(404, "not_found", "mapping not found")
    return out(m)
