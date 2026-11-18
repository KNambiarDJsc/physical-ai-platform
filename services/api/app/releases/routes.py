"""Register releases. A release is an OpenMHS deployment manifest; its digest is the engine's identity for it."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from openmhs_bridge import digest
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import ProjectEngineer, ProjectViewer, audit_allow, error
from ..db import get_session
from .models import Release

router = APIRouter(prefix="/api/v1/orgs/{org_slug}/projects/{project_slug}/releases", tags=["releases"])
SessionDep = Annotated[Session, Depends(get_session)]
LABEL = r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,99}$"
IMMUTABLE = re.compile(r"(sha256:[0-9a-f]{64}|(^|[@/:])[0-9a-f]{7,64})$")


class Component(BaseModel):
    model_config = {"extra": "allow"}
    kind: Literal["software", "model", "firmware", "hardware", "calibration", "config"]
    name: str = Field(min_length=1, max_length=200)


class ReleaseIn(BaseModel):
    label: str = Field(pattern=LABEL)
    kind: Literal["software", "policy"]
    components: list[Component] = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ReleaseOut(BaseModel):
    id: uuid.UUID
    label: str
    kind: str
    description: str | None
    manifest: dict[str, Any]
    manifest_digest: str
    created_at: datetime


def out(r: Release) -> ReleaseOut:
    return ReleaseOut(
        id=r.id,
        label=r.label,
        kind=r.kind,
        description=r.description,
        manifest=r.manifest,
        manifest_digest=r.manifest_digest,
        created_at=r.created_at,
    )


def build_manifest(body: ReleaseIn) -> dict[str, Any]:
    components = [c.model_dump(mode="json") for c in body.components]
    if body.kind == "policy":
        models = [c for c in components if c["kind"] == "model"]
        immutable = [
            c
            for c in models
            if IMMUTABLE.search(str(c.get("checkpoint_digest", ""))) or IMMUTABLE.search(str(c.get("revision", "")))
        ]
        if not immutable:
            raise error(
                422,
                "release.model_revision",
                "a policy release needs a model component with an immutable revision (a commit or sha256 digest), "
                "not a tag",
            )
    return {"schema": "openmhs.deployment/0.1", "components": components, "labels": {"release": body.label}}


@router.post("", status_code=201)
def create_release(body: ReleaseIn, ctx: ProjectEngineer, session: SessionDep) -> ReleaseOut:
    manifest = build_manifest(body)
    try:
        manifest_digest = digest(manifest)
    except ValueError as e:
        raise error(422, "release.manifest", str(e)) from e
    r = Release(
        project_id=ctx.project.id,
        label=body.label,
        kind=body.kind,
        description=body.description,
        manifest=manifest,
        manifest_digest=manifest_digest,
        created_by=ctx.principal.label,
    )
    session.add(r)
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise error(409, "conflict", "a release with this label exists in the project") from e
    audit_allow(session, ctx, "release.create", f"release:{r.id}", digest=manifest_digest)
    session.commit()
    return out(r)


@router.get("")
def list_releases(ctx: ProjectViewer, session: SessionDep) -> list[ReleaseOut]:
    rows = session.scalars(select(Release).where(Release.project_id == ctx.project.id).order_by(Release.created_at))
    return [out(r) for r in rows]


@router.get("/{release_id}")
def get_release(release_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> ReleaseOut:
    r = session.scalar(select(Release).where(Release.id == release_id, Release.project_id == ctx.project.id))
    if r is None:
        raise error(404, "not_found", "release not found")
    return out(r)
