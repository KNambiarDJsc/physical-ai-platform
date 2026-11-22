"""Digital twin API: robot model versions (URDF + meshes) and MCAP recordings with their decoded playback tracks.

Viewers read; engineers create. Everything is project-scoped, so another workspace gets 404 exactly as elsewhere.
Uploads are untrusted: bounded, content-checked, never used as paths (files are addressed by their digest).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import SLUG, ProjectEngineer, ProjectViewer, audit_allow, error
from ..db import get_session
from ..evaluations.models import EpisodeRecord
from ..evidence.storage import Storage, TooLarge, get_storage
from ..releases.models import Release
from .models import Recording, RobotModel, RobotModelVersion
from .track import RecordingError, build_track, track_sha256
from .urdf import ALLOWED_EXT, MAX_MESH_BYTES, MAX_URDF_BYTES, ModelError, check_path, check_stl, parse_urdf

router = APIRouter(prefix="/api/v1/orgs/{org_slug}/projects/{project_slug}/twin", tags=["twin"])
SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[Storage, Depends(get_storage)]

MAX_FILES = 64
MAX_MODEL_BYTES = 32 * 1024 * 1024
MAX_RECORDING_BYTES = 96 * 1024 * 1024
MCAP_MAGIC = b"\x89MCAP0\r\n"
SHA = r"^sha256:[0-9a-f]{64}$"


class FileRef(BaseModel):
    path: str = Field(max_length=200)
    sha256: str = Field(pattern=SHA)


class Omitted(BaseModel):
    path: str = Field(max_length=300)
    reason: str = Field(max_length=300)


class Source(BaseModel):
    repository: str = Field(min_length=1, max_length=200)
    commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    path: str | None = Field(default=None, max_length=300)
    license_spdx: str = Field(min_length=1, max_length=80)
    notice: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=1000)


class Manifest(BaseModel):
    slug: str = Field(pattern=SLUG)
    name: str = Field(min_length=1, max_length=200)
    urdf: str = Field(max_length=200)
    files: list[FileRef] = Field(min_length=1, max_length=MAX_FILES)
    source: Source
    omitted: list[Omitted] = Field(default_factory=list, max_length=200)


class VersionSummary(BaseModel):
    number: int
    manifest_sha256: str
    source_repository: str
    source_commit: str
    license_spdx: str
    created_at: datetime


class ModelOut(BaseModel):
    slug: str
    name: str
    versions: list[VersionSummary]


class FileOut(BaseModel):
    path: str
    sha256: str
    size_bytes: int
    media_type: str


class VersionOut(BaseModel):
    model_slug: str
    model_name: str
    number: int
    manifest_sha256: str
    urdf_path: str
    source: dict[str, Any]
    files: list[FileOut]
    omitted: list[dict[str, Any]]
    structure: dict[str, Any]
    created_at: datetime
    created_by: str


def _canonical(m: Manifest) -> str:
    body = {
        "slug": m.slug,
        "urdf": m.urdf,
        "files": sorted(({"path": f.path, "sha256": f.sha256} for f in m.files), key=lambda f: f["path"]),
        "source": m.source.model_dump(),
        "omitted": sorted((o.model_dump() for o in m.omitted), key=lambda o: o["path"]),
    }
    return "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _version_out(model: RobotModel, v: RobotModelVersion) -> VersionOut:
    return VersionOut(
        model_slug=model.slug,
        model_name=model.name,
        number=v.number,
        manifest_sha256=v.manifest_sha256,
        urdf_path=v.urdf_path,
        source=v.source,
        files=[FileOut(**{k: f[k] for k in ("path", "sha256", "size_bytes", "media_type")}) for f in v.files],
        omitted=v.omitted,
        structure=v.structure,
        created_at=v.created_at,
        created_by=v.created_by,
    )


def _read_limited(f: UploadFile, limit: int) -> bytes:
    data = f.file.read(limit + 1)
    if len(data) > limit:
        raise error(413, "twin.too_large", f"a file is larger than {limit} bytes")
    return data


@router.post("/models", status_code=201, responses={200: {"description": "this exact version already exists"}})
def create_model_version(
    ctx: ProjectEngineer,
    session: SessionDep,
    storage: StorageDep,
    response: Response,
    manifest: Annotated[str, Form(max_length=200_000)],
    files: Annotated[list[UploadFile], File()],
) -> VersionOut:
    try:
        m = Manifest.model_validate_json(manifest)
    except ValidationError as e:
        raise error(
            422, "twin.manifest", "the manifest is invalid: " + "; ".join(x["msg"] for x in e.errors()[:5])
        ) from None
    if len(files) != len(m.files):
        raise error(422, "twin.files", "send one uploaded file per manifest entry, in the same order")
    blobs: dict[str, bytes] = {}
    total = 0
    for ref, up in zip(m.files, files, strict=True):
        if ref.path in blobs:
            raise error(422, "twin.files", f"{ref.path!r} is listed twice")
        try:
            ext = check_path(ref.path)
        except ModelError as e:
            raise error(422, "twin.path", str(e)) from None
        data = _read_limited(up, MAX_URDF_BYTES if ext == ".urdf" else MAX_MESH_BYTES)
        total += len(data)
        if total > MAX_MODEL_BYTES:
            raise error(413, "twin.too_large", f"a model version is limited to {MAX_MODEL_BYTES} bytes")
        if "sha256:" + hashlib.sha256(data).hexdigest() != ref.sha256:
            raise error(422, "twin.digest", f"{ref.path!r} does not match its declared sha256")
        if ext == ".stl":
            try:
                check_stl(ref.path, data)
            except ModelError as e:
                raise error(422, "twin.stl", str(e)) from None
        blobs[ref.path] = data
    if m.urdf not in blobs or not m.urdf.lower().endswith(".urdf"):
        raise error(422, "twin.urdf", "the manifest's urdf must be one of its files and end in .urdf")
    try:
        parsed = parse_urdf(blobs[m.urdf], {p for p in blobs if p != m.urdf})
    except ModelError as e:
        raise error(422, "twin.urdf", str(e)) from None
    unused = sorted(p for p in blobs if p != m.urdf and p not in parsed.mesh_refs)
    if unused:
        raise error(422, "twin.unreferenced", f"files the URDF does not reference: {', '.join(unused)}")

    digest = _canonical(m)
    model = session.scalar(select(RobotModel).where(RobotModel.project_id == ctx.project.id, RobotModel.slug == m.slug))
    if model is None:
        model = RobotModel(project_id=ctx.project.id, slug=m.slug, name=m.name)
        session.add(model)
        session.flush()
    existing = session.scalar(
        select(RobotModelVersion).where(
            RobotModelVersion.model_id == model.id, RobotModelVersion.manifest_sha256 == digest
        )
    )
    if existing is not None:
        response.status_code = 200
        return _version_out(model, existing)
    stored: list[dict[str, Any]] = []
    for ref in sorted(m.files, key=lambda f: f.path):
        try:
            s = storage.put([blobs[ref.path]], MAX_MESH_BYTES)
        except TooLarge:
            raise error(413, "twin.too_large", "a file is too large") from None
        stored.append(
            {
                "path": ref.path,
                "sha256": s.sha256,
                "size_bytes": s.size,
                "media_type": ALLOWED_EXT["." + ref.path.rsplit(".", 1)[-1].lower()],
                "storage_key": s.key,
            }
        )
    number = (
        session.scalar(select(func.max(RobotModelVersion.number)).where(RobotModelVersion.model_id == model.id)) or 0
    ) + 1
    v = RobotModelVersion(
        model_id=model.id,
        project_id=ctx.project.id,
        number=number,
        manifest_sha256=digest,
        urdf_path=m.urdf,
        source=m.source.model_dump(),
        files=stored,
        omitted=[o.model_dump() for o in m.omitted],
        structure=parsed.structure,
        created_by=ctx.principal.label,
    )
    session.add(v)
    session.flush()
    audit_allow(session, ctx, "twin.model.create", f"robot_model:{model.id}", version=number, manifest=digest)
    session.commit()
    return _version_out(model, v)


@router.get("/models")
def list_models(ctx: ProjectViewer, session: SessionDep) -> list[ModelOut]:
    models = session.scalars(
        select(RobotModel).where(RobotModel.project_id == ctx.project.id).order_by(RobotModel.slug)
    ).all()
    out = []
    for mod in models:
        vs = session.scalars(
            select(RobotModelVersion).where(RobotModelVersion.model_id == mod.id).order_by(RobotModelVersion.number)
        ).all()
        out.append(
            ModelOut(
                slug=mod.slug,
                name=mod.name,
                versions=[
                    VersionSummary(
                        number=v.number,
                        manifest_sha256=v.manifest_sha256,
                        source_repository=v.source["repository"],
                        source_commit=v.source["commit"],
                        license_spdx=v.source["license_spdx"],
                        created_at=v.created_at,
                    )
                    for v in vs
                ],
            )
        )
    return out


def _version(session: Session, ctx: ProjectViewer, slug: str, number: int) -> tuple[RobotModel, RobotModelVersion]:
    model = session.scalar(select(RobotModel).where(RobotModel.project_id == ctx.project.id, RobotModel.slug == slug))
    v = (
        session.scalar(
            select(RobotModelVersion).where(RobotModelVersion.model_id == model.id, RobotModelVersion.number == number)
        )
        if model
        else None
    )
    if model is None or v is None:
        raise error(404, "not_found", "model version not found")
    return model, v


@router.get("/models/{model_slug}/versions/{number}")
def get_model_version(
    model_slug: Annotated[str, Field(pattern=SLUG)], number: int, ctx: ProjectViewer, session: SessionDep
) -> VersionOut:
    model, v = _version(session, ctx, model_slug, number)
    return _version_out(model, v)


@router.get("/models/{model_slug}/versions/{number}/files/{file_path:path}")
def get_model_file(
    model_slug: str, number: int, file_path: str, ctx: ProjectViewer, session: SessionDep, storage: StorageDep
) -> Response:
    _, v = _version(session, ctx, model_slug, number)
    f = next((x for x in v.files if x["path"] == file_path), None)  # looked up in the list, never joined to a path
    if f is None:
        raise error(404, "not_found", "file not found in this version")
    return Response(
        storage.get(f["storage_key"]),
        media_type=f["media_type"],
        headers={
            "ETag": f'"{f["sha256"]}"',
            "Cache-Control": "private, immutable, max-age=31536000",
            "X-Content-Type-Options": "nosniff",
        },
    )


# --- recordings -------------------------------------------------------------------------------------------------


class EpisodeLink(BaseModel):
    id: uuid.UUID
    evaluation_id: uuid.UUID
    release_id: uuid.UUID
    release_label: str
    episode_key: str
    robot: str
    scenario: str | None
    reported: str
    verdict: str | None
    outcome_class: str
    reasons: list[str]


class RecordingOut(BaseModel):
    id: uuid.UUID
    label: str
    filename: str
    sha256: str
    size_bytes: int
    clock: str
    duration_s: float
    model: str | None
    episode: EpisodeLink | None
    created_at: datetime
    created_by: str


class RecordingDetail(RecordingOut):
    summary: dict[str, Any] | None
    identity: dict[str, Any] | None
    track_sha256: str
    counts: dict[str, int]
    frames: dict[str, Any]
    limits: dict[str, Any]
    events: list[dict[str, Any]]
    model_version: VersionSummary | None


def _episode_link(session: Session, ep_id: uuid.UUID | None) -> EpisodeLink | None:
    if ep_id is None:
        return None
    e = session.get(EpisodeRecord, ep_id)
    if e is None:
        return None
    rel = session.get(Release, e.release_id)
    return EpisodeLink(
        id=e.id,
        evaluation_id=e.job_id,
        release_id=e.release_id,
        release_label=rel.label if rel else "",
        episode_key=e.episode_key,
        robot=e.robot,
        scenario=e.scenario,
        reported=e.reported,
        verdict=e.verdict,
        outcome_class=e.outcome_class,
        reasons=list(e.reasons or []),
    )


def _model_label(session: Session, vid: uuid.UUID | None) -> tuple[str | None, RobotModelVersion | None]:
    if vid is None:
        return None, None
    v = session.get(RobotModelVersion, vid)
    if v is None:
        return None, None
    model = session.get(RobotModel, v.model_id)
    return (f"{model.slug}@{v.number}" if model else None), v


def _rec_out(session: Session, r: Recording) -> RecordingOut:
    label, _ = _model_label(session, r.model_version_id)
    return RecordingOut(
        id=r.id,
        label=r.label,
        filename=r.filename,
        sha256=r.sha256,
        size_bytes=r.size_bytes,
        clock=r.track["clock"],
        duration_s=r.track["duration_s"],
        model=label,
        episode=_episode_link(session, r.episode_id),
        created_at=r.created_at,
        created_by=r.created_by,
    )


def _json_form(raw: str | None, what: str, schema: str) -> dict[str, Any] | None:
    if raw is None or not raw.strip():
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        raise error(422, "twin.json", f"{what} is not JSON") from None
    if not isinstance(d, dict) or d.get("schema") != schema:
        raise error(422, "twin.json", f"{what} must be a JSON object with schema {schema!r}")
    return d


@router.post("/recordings", status_code=201, responses={200: {"description": "this recording is already stored"}})
def create_recording(
    ctx: ProjectEngineer,
    session: SessionDep,
    storage: StorageDep,
    response: Response,
    file: Annotated[UploadFile, File()],
    label: Annotated[str, Form(min_length=1, max_length=200)],
    summary: Annotated[str | None, Form(max_length=2_000_000)] = None,
    identity: Annotated[str | None, Form(max_length=200_000)] = None,
    model_slug: Annotated[str | None, Form(pattern=SLUG)] = None,
    model_version: Annotated[int | None, Form(ge=1)] = None,
    episode_id: Annotated[uuid.UUID | None, Form()] = None,
) -> RecordingOut:
    name = re.split(r"[\\/]", file.filename or "")[-1]
    name = "".join(c for c in name if c.isprintable())[:200].lstrip(".") or "recording.mcap"
    if not name.lower().endswith(".mcap"):
        raise error(415, "twin.type", "a recording is an .mcap file")
    data = _read_limited(file, MAX_RECORDING_BYTES)
    if not data.startswith(MCAP_MAGIC):
        raise error(415, "twin.type", "the file is not an MCAP file")
    sha = "sha256:" + hashlib.sha256(data).hexdigest()
    summ = _json_form(summary, "summary", "pap.ros.bag-summary/1")
    ident = _json_form(identity, "identity", "pap.ros.run-identity/1")
    if summ is not None:
        listed = {f.get("sha256") for f in summ.get("files", []) if str(f.get("name", "")).endswith(".mcap")}
        if sha.removeprefix("sha256:") not in listed and sha not in listed:
            raise error(422, "twin.summary", "the summary does not describe this file (its sha256 is not listed)")
    existing = session.scalar(select(Recording).where(Recording.project_id == ctx.project.id, Recording.sha256 == sha))
    if existing is not None:
        response.status_code = 200
        return _rec_out(session, existing)
    mv: RobotModelVersion | None = None
    if (model_slug is None) != (model_version is None):
        raise error(422, "twin.model", "give both model_slug and model_version, or neither")
    if model_slug is not None and model_version is not None:
        _, mv = _version(session, ctx, model_slug, model_version)
    ep: EpisodeRecord | None = None
    if episode_id is not None:
        ep = session.scalar(
            select(EpisodeRecord).where(EpisodeRecord.id == episode_id, EpisodeRecord.project_id == ctx.project.id)
        )
        if ep is None:
            raise error(404, "not_found", "episode not found")
    try:
        track = build_track(data, summ)
    except RecordingError as e:
        raise error(422, "twin.recording", str(e)) from None
    stored = storage.put([data], MAX_RECORDING_BYTES)
    r = Recording(
        project_id=ctx.project.id,
        label=label,
        filename=name,
        sha256=sha,
        size_bytes=stored.size,
        storage_key=stored.key,
        summary=summ,
        identity=ident,
        model_version_id=mv.id if mv else None,
        episode_id=ep.id if ep else None,
        track=track,
        track_sha256=track_sha256(track),
        created_by=ctx.principal.label,
    )
    session.add(r)
    session.flush()
    audit_allow(session, ctx, "twin.recording.create", f"recording:{r.id}", sha256=sha, bytes=r.size_bytes)
    session.commit()
    return _rec_out(session, r)


@router.get("/recordings")
def list_recordings(ctx: ProjectViewer, session: SessionDep) -> list[RecordingOut]:
    rows = session.scalars(
        select(Recording).where(Recording.project_id == ctx.project.id).order_by(Recording.created_at.desc())
    )
    return [_rec_out(session, r) for r in rows]


def _recording(session: Session, ctx: ProjectViewer, recording_id: uuid.UUID) -> Recording:
    r = session.scalar(select(Recording).where(Recording.id == recording_id, Recording.project_id == ctx.project.id))
    if r is None:
        raise error(404, "not_found", "recording not found")
    return r


@router.get("/recordings/{recording_id}")
def get_recording(recording_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> RecordingDetail:
    r = _recording(session, ctx, recording_id)
    base = _rec_out(session, r)
    _, mv = _model_label(session, r.model_version_id)
    return RecordingDetail(
        **base.model_dump(),
        summary=r.summary,
        identity=r.identity,
        track_sha256=r.track_sha256,
        counts=r.track["counts"],
        frames=r.track["frames"],
        limits=r.track["limits"],
        events=r.track["events"],
        model_version=VersionSummary(
            number=mv.number,
            manifest_sha256=mv.manifest_sha256,
            source_repository=mv.source["repository"],
            source_commit=mv.source["commit"],
            license_spdx=mv.source["license_spdx"],
            created_at=mv.created_at,
        )
        if mv
        else None,
    )


@router.get("/recordings/{recording_id}/track")
def get_track(recording_id: uuid.UUID, ctx: ProjectViewer, session: SessionDep) -> Response:
    r = _recording(session, ctx, recording_id)
    return Response(
        json.dumps(r.track, sort_keys=True, separators=(",", ":")),
        media_type="application/json",
        headers={"ETag": f'"{r.track_sha256}"', "Cache-Control": "private, max-age=3600"},
    )
