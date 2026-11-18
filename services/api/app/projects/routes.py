from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import SLUG, AdminDep, ProjectViewer, ViewerDep, audit_allow, error
from ..db import get_session
from .models import Project

router = APIRouter(prefix="/api/v1/orgs/{org_slug}/projects", tags=["projects"])
SessionDep = Annotated[Session, Depends(get_session)]


class ProjectIn(BaseModel):
    slug: str = Field(pattern=SLUG)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    created_at: datetime


def out(p: Project) -> ProjectOut:
    return ProjectOut(id=p.id, slug=p.slug, name=p.name, description=p.description, created_at=p.created_at)


@router.post("", status_code=201)
def create_project(body: ProjectIn, ctx: AdminDep, session: SessionDep) -> ProjectOut:
    p = Project(organization_id=ctx.org.id, slug=body.slug, name=body.name, description=body.description)
    session.add(p)
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise error(409, "conflict", "project slug is taken in this organization") from e
    audit_allow(session, ctx, "project.create", f"project:{p.id}")
    session.commit()
    return out(p)


@router.get("")
def list_projects(ctx: ViewerDep, session: SessionDep) -> list[ProjectOut]:
    rows = session.scalars(select(Project).where(Project.organization_id == ctx.org.id).order_by(Project.slug))
    return [out(p) for p in rows]


@router.get("/{project_slug}")
def get_project(ctx: ProjectViewer) -> ProjectOut:
    return out(ctx.project)
