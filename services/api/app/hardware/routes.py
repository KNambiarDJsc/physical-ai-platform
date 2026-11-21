"""Hardware Hub API: the operator's environment catalog, a workspace's environments, discovery, devices."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from pap_device_sdk import AdapterError
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import SLUG, AdminDep, EngineerDep, PrincipalDep, ViewerDep, audit_allow, error
from ..config import Settings, get_settings
from ..db import get_session, utcnow
from .models import Capability, Device, Environment
from .service import EnvironmentUnavailable, adapter_for, catalog_entry, record_discovery

router = APIRouter(prefix="/api/v1", tags=["hardware"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class CatalogEntryOut(BaseModel):
    key: str
    name: str
    kind: str
    adapter: str
    endpoint: str
    description: str


class EnvironmentIn(BaseModel):
    config_key: str = Field(pattern=SLUG)
    slug: str | None = Field(default=None, pattern=SLUG)
    name: str | None = Field(default=None, min_length=1, max_length=120)


class EnvironmentOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    kind: str
    adapter: str
    config_key: str
    available: bool  # still offered by the operator
    endpoint: str | None
    devices: int
    last_discovered_at: datetime | None
    created_at: datetime


class CapabilityOut(BaseModel):
    kind: str
    name: str
    title: str
    description: str
    read_only: bool
    data_schema: dict[str, Any]
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    idempotency_key: str | None


class DeviceOut(BaseModel):
    id: uuid.UUID
    environment: str
    environment_kind: str
    key: str
    title: str
    description: str
    protocol: str
    td_sha256: str
    declares_simulated: bool
    present: bool
    updated_at: datetime
    capabilities: list[CapabilityOut]


class DeviceDetailOut(DeviceOut):
    description_document: dict[str, Any]


class DiscoveryOut(BaseModel):
    environment: str
    found: int
    new: int
    changed: int
    missing: int
    devices: list[DeviceOut]


class PropertyReadOut(BaseModel):
    device: str
    name: str
    value: Any
    read_at: datetime


def _env_out(e: Environment, settings: Settings, devices: int) -> EnvironmentOut:
    cfg = catalog_entry(settings, e.config_key)
    return EnvironmentOut(
        id=e.id, slug=e.slug, name=e.name, kind=e.kind, adapter=e.adapter, config_key=e.config_key,
        available=cfg is not None, endpoint=cfg.endpoint if cfg else None, devices=devices,
        last_discovered_at=e.last_discovered_at, created_at=e.created_at,
    )  # fmt: skip


def device_out(session: Session, d: Device, env: Environment, *, detail: bool = False) -> DeviceOut:
    caps = session.scalars(
        select(Capability).where(Capability.device_id == d.id).order_by(Capability.kind, Capability.name)
    )
    base: dict[str, Any] = dict(
        id=d.id, environment=env.slug, environment_kind=env.kind, key=d.key, title=d.title, description=d.description,
        protocol=d.protocol, td_sha256=d.td_sha256, declares_simulated=d.declares_simulated, present=d.present,
        updated_at=d.updated_at,
        capabilities=[
            CapabilityOut(kind=c.kind, name=c.name, title=c.title, description=c.description, read_only=c.read_only,
                          data_schema=c.data_schema, input_schema=c.input_schema, output_schema=c.output_schema,
                          idempotency_key=c.idempotency_key)
            for c in caps
        ],
    )  # fmt: skip
    return DeviceDetailOut(**base, description_document=d.description_document) if detail else DeviceOut(**base)


def _environment(session: Session, org_id: uuid.UUID, slug: str) -> Environment:
    env = session.scalar(select(Environment).where(Environment.organization_id == org_id, Environment.slug == slug))
    if env is None:
        raise error(404, "not_found", "environment not found")
    return env


def _device(session: Session, org_id: uuid.UUID, device_id: uuid.UUID) -> tuple[Device, Environment]:
    d = session.scalar(select(Device).where(Device.organization_id == org_id, Device.id == device_id))
    if d is None:
        raise error(404, "not_found", "device not found")
    env = session.get(Environment, d.environment_id)
    assert env is not None
    return d, env


@router.get("/environment-catalog")
def environment_catalog(_: PrincipalDep, settings: SettingsDep) -> list[CatalogEntryOut]:
    """The environments this installation's operator allows workspaces to connect."""
    return [CatalogEntryOut(**e.model_dump()) for e in settings.environments]


@router.post("/orgs/{org_slug}/environments", status_code=201)
def connect_environment(
    body: EnvironmentIn, ctx: AdminDep, session: SessionDep, settings: SettingsDep
) -> EnvironmentOut:
    cfg = catalog_entry(settings, body.config_key)
    if cfg is None:
        raise error(422, "unknown_environment", "this installation does not offer that environment")
    env = Environment(
        organization_id=ctx.org.id, slug=body.slug or cfg.key, name=body.name or cfg.name, kind=cfg.kind,
        adapter=cfg.adapter, config_key=cfg.key,
    )  # fmt: skip
    session.add(env)
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise error(409, "conflict", "this workspace already has an environment with that slug") from e
    audit_allow(session, ctx, "environment.connect", f"environment:{env.id}", config_key=cfg.key, kind=cfg.kind)
    session.commit()
    return _env_out(env, settings, 0)


@router.get("/orgs/{org_slug}/environments")
def list_environments(ctx: ViewerDep, session: SessionDep, settings: SettingsDep) -> list[EnvironmentOut]:
    rows = session.execute(
        select(Device.environment_id, func.count())
        .where(Device.organization_id == ctx.org.id, Device.present.is_(True))
        .group_by(Device.environment_id)
    ).all()
    counts: dict[uuid.UUID, int] = {r[0]: int(r[1]) for r in rows}
    envs = session.scalars(
        select(Environment).where(Environment.organization_id == ctx.org.id).order_by(Environment.slug)
    )
    return [_env_out(e, settings, int(counts.get(e.id, 0))) for e in envs]


@router.post("/orgs/{org_slug}/environments/{env_slug}/discover")
def discover(
    env_slug: Annotated[str, Path(pattern=SLUG)], ctx: EngineerDep, session: SessionDep, settings: SettingsDep
) -> DiscoveryOut:
    """Ask the environment what devices it has and what each can do. Reads descriptions only."""
    env = _environment(session, ctx.org.id, env_slug)
    try:
        found = adapter_for(env, settings).discover()
    except EnvironmentUnavailable as e:
        raise error(409, "environment_unavailable", "the operator no longer offers this environment") from e
    except AdapterError as e:
        raise error(502, "discovery_failed", str(e)) from e
    summary = record_discovery(session, env, found)
    audit_allow(session, ctx, "environment.discover", f"environment:{env.id}", found=summary.found, new=summary.new)
    session.commit()
    devices = session.scalars(select(Device).where(Device.environment_id == env.id).order_by(Device.key))
    return DiscoveryOut(
        environment=env.slug, found=summary.found, new=summary.new, changed=summary.changed, missing=summary.missing,
        devices=[device_out(session, d, env) for d in devices],
    )  # fmt: skip


@router.get("/orgs/{org_slug}/devices")
def list_devices(ctx: ViewerDep, session: SessionDep) -> list[DeviceOut]:
    rows = session.execute(
        select(Device, Environment)
        .join(Environment, Environment.id == Device.environment_id)
        .where(Device.organization_id == ctx.org.id)
        .order_by(Environment.slug, Device.key)
    ).all()
    return [device_out(session, d, e) for d, e in rows]


@router.get("/orgs/{org_slug}/devices/{device_id}")
def get_device(device_id: uuid.UUID, ctx: ViewerDep, session: SessionDep) -> DeviceDetailOut:
    d, env = _device(session, ctx.org.id, device_id)
    out = device_out(session, d, env, detail=True)
    assert isinstance(out, DeviceDetailOut)
    return out


@router.get("/orgs/{org_slug}/devices/{device_id}/properties/{name}")
def read_property(
    device_id: uuid.UUID,
    name: Annotated[str, Path(pattern=r"^[A-Za-z0-9_.-]{1,128}$")],
    ctx: ViewerDep,
    session: SessionDep,
    settings: SettingsDep,
) -> PropertyReadOut:
    """Read one property live. Observation: allowed for every environment kind."""
    d, env = _device(session, ctx.org.id, device_id)
    cap = session.scalar(
        select(Capability).where(Capability.device_id == d.id, Capability.kind == "property", Capability.name == name)
    )
    if cap is None:
        raise error(404, "not_found", "the device has no such property")
    try:
        value = adapter_for(env, settings).read_property(d.key, name)
    except EnvironmentUnavailable as e:
        raise error(409, "environment_unavailable", "the operator no longer offers this environment") from e
    except AdapterError as e:
        raise error(502, "device_unreachable", str(e)) from e
    return PropertyReadOut(device=d.key, name=name, value=value, read_at=utcnow())
