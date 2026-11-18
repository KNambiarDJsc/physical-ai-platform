"""Upload and list source artifacts. Uploads are untrusted: size-limited, sniffed, never used as paths."""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, BinaryIO

from fastapi import APIRouter, Depends, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import ProjectEngineer, ProjectViewer, audit_allow, error
from ..config import Settings, get_settings
from ..db import get_session
from .models import Artifact
from .storage import Storage, TooLarge, get_storage

router = APIRouter(prefix="/api/v1/orgs/{org_slug}/projects/{project_slug}/artifacts", tags=["evidence"])
SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[Storage, Depends(get_storage)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

ALLOWED = {".csv": "text/csv", ".jsonl": "application/x-ndjson", ".json": "application/json"}
ARCHIVE_MAGIC = (b"PK\x03\x04", b"\x1f\x8b", b"BZh", b"\xfd7zXZ\x00", b"7z\xbc\xaf\x27\x1c", b"Rar!")
CHUNK = 1024 * 1024


class ArtifactOut(BaseModel):
    id: uuid.UUID
    sha256: str
    size_bytes: int
    media_type: str
    filename: str
    kind: str
    created_at: datetime
    created_by: str


def out(a: Artifact) -> ArtifactOut:
    return ArtifactOut(
        id=a.id,
        sha256=a.sha256,
        size_bytes=a.size_bytes,
        media_type=a.media_type,
        filename=a.filename,
        kind=a.kind,
        created_at=a.created_at,
        created_by=a.created_by,
    )


def display_name(raw: str | None) -> str:
    """A safe label for humans: last path component, no control characters, bounded. Never a path."""
    name = re.split(r"[\\/]", raw or "")[-1]
    name = "".join(c for c in unicodedata.normalize("NFC", name) if unicodedata.category(c)[0] != "C")
    name = name.strip().lstrip(".")[:200]
    return name or "upload"


def _chunks(f: BinaryIO, first: bytes) -> Iterator[bytes]:
    yield first
    while block := f.read(CHUNK):
        yield block


@router.post("", status_code=201)
def upload(
    file: UploadFile,
    ctx: ProjectEngineer,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    request: Request,
) -> ArtifactOut:
    limit = settings.max_upload_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + 64 * 1024:
        raise error(413, "upload.too_large", f"uploads are limited to {limit} bytes")
    name = display_name(file.filename)
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise error(415, "upload.type", f"accepted: {', '.join(sorted(ALLOWED))}; archives are not accepted yet")
    head = file.file.read(8192)
    if any(head.startswith(m) for m in ARCHIVE_MAGIC):
        raise error(415, "upload.archive", "archives are not accepted yet (no extraction protection in place)")
    if b"\x00" in head:
        raise error(415, "upload.binary", "the file is not text")
    try:
        stored = storage.put(_chunks(file.file, head), limit)
    except TooLarge as e:
        raise error(413, "upload.too_large", f"uploads are limited to {limit} bytes") from e
    existing = session.scalar(
        select(Artifact).where(Artifact.project_id == ctx.project.id, Artifact.sha256 == stored.sha256)
    )
    if existing is not None:
        return out(existing)
    a = Artifact(
        project_id=ctx.project.id,
        sha256=stored.sha256,
        size_bytes=stored.size,
        media_type=ALLOWED[ext],
        filename=name,
        storage_key=stored.key,
        kind="source",
        created_by=ctx.principal.label,
    )
    session.add(a)
    session.flush()
    audit_allow(session, ctx, "artifact.upload", f"artifact:{a.id}", sha256=a.sha256, bytes=a.size_bytes)
    session.commit()
    return out(a)


@router.get("")
def list_artifacts(ctx: ProjectViewer, session: SessionDep) -> list[ArtifactOut]:
    rows = session.scalars(
        select(Artifact).where(Artifact.project_id == ctx.project.id).order_by(Artifact.created_at.desc())
    )
    return [out(a) for a in rows]


@router.get("/{artifact_id}")
def get_artifact(artifact_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> ArtifactOut:
    a = session.scalar(select(Artifact).where(Artifact.id == artifact_id, Artifact.project_id == ctx.project.id))
    if a is None:
        raise error(404, "not_found", "artifact not found")
    return out(a)
