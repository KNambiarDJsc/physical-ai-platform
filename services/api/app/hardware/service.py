"""Discovery: ask the environment's adapter what is there, and record it. Reads only; never commands a device."""

from __future__ import annotations

from dataclasses import dataclass

from pap_device_sdk import DeviceAdapter, DiscoveredDevice, WotHttpAdapter
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import EnvironmentConfig, Settings
from ..db import utcnow
from .models import Capability, Device, Environment


class EnvironmentUnavailable(Exception):
    """The operator no longer offers this environment (its PAP_ENVIRONMENTS entry was removed)."""


def catalog_entry(settings: Settings, key: str) -> EnvironmentConfig | None:
    return next((e for e in settings.environments if e.key == key), None)


def adapter_for(env: Environment, settings: Settings) -> DeviceAdapter:
    cfg = catalog_entry(settings, env.config_key)
    if cfg is None:
        raise EnvironmentUnavailable(env.config_key)
    if cfg.adapter == "wot-http":
        return WotHttpAdapter(cfg.endpoint, timeout_s=settings.device_timeout_s)
    raise EnvironmentUnavailable(f"{env.config_key}: adapter {cfg.adapter} is not available")


@dataclass
class DiscoverySummary:
    found: int
    new: int
    changed: int
    missing: int


def _capabilities(device: Device, found: DiscoveredDevice) -> list[Capability]:
    return [
        Capability(
            device_id=device.id,
            kind=a.kind,
            name=a.name,
            title=a.title[:500],
            description=a.description,
            read_only=a.read_only,
            data_schema=a.data_schema,
            input_schema=a.input_schema,
            output_schema=a.output_schema,
            idempotency_key=a.idempotency_key,
        )
        for a in found.affordances
    ]


def record_discovery(session: Session, env: Environment, found: list[DiscoveredDevice]) -> DiscoverySummary:
    existing = {d.key: d for d in session.scalars(select(Device).where(Device.environment_id == env.id))}
    new = changed = 0
    now = utcnow()
    for f in found:
        d = existing.pop(f.key, None)
        if d is None:
            d = Device(organization_id=env.organization_id, environment_id=env.id, key=f.key)
            session.add(d)
            new += 1
        elif d.td_sha256 != f.td_sha256 or not d.present:
            changed += 1
        else:
            d.present = True
            d.updated_at = now
            continue
        d.title, d.description, d.protocol = f.title[:300], f.description, f.protocol
        d.td_sha256, d.declares_simulated, d.description_document = (
            f.td_sha256,
            f.declares_simulated,
            f.description_document,
        )
        d.present, d.updated_at = True, now
        session.flush()
        session.execute(delete(Capability).where(Capability.device_id == d.id))
        session.add_all(_capabilities(d, f))
    for gone in existing.values():  # in the registry, not at the endpoint any more: kept, marked missing
        gone.present = False
        gone.updated_at = now
    env.last_discovered_at = now
    session.flush()
    return DiscoverySummary(found=len(found), new=new, changed=changed, missing=len(existing))
