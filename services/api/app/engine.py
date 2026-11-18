"""The application's handle on the pinned OpenMHS engine (one per process)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from openmhs_bridge import Engine, EngineError, engine_from_env

from .config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    from .observability import engine_observer

    s = get_settings()
    engine = engine_from_env(s.engine_lock_path, timeout_s=s.engine_timeout_s)
    engine.observers.append(engine_observer)
    return engine


def engine_status() -> dict[str, Any]:
    """For /healthz: is the pinned engine present, with the right digest, and does it run?"""
    try:
        engine = get_engine()
        p = engine.provenance()
        return {"ok": True, "version": p.version, "commit": p.commit, "binary_sha256": p.binary_sha256}
    except EngineError as e:
        get_engine.cache_clear()
        return {"ok": False, "error": e.code, "message": e.message}
