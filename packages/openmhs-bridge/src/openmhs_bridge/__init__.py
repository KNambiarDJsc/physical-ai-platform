"""Bridge to the pinned OpenMHS engine. See ARCHITECTURE.md, "The engine boundary"."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .canonical import canonical_json, digest, sha256_bytes, sha256_file
from .conditions import conditions_of
from .engine import VERDICT_EXIT, Engine, EngineConfig, RawRun, Result
from .errors import EngineError
from .models import (
    Arm,
    Comparison,
    EngineProvenance,
    IncidentDetail,
    IncidentSummary,
    IngestResult,
    Paired,
    Stratum,
    VerifierReport,
)

__all__ = [
    "VERDICT_EXIT",
    "Arm",
    "Comparison",
    "Engine",
    "EngineConfig",
    "EngineError",
    "EngineProvenance",
    "IncidentDetail",
    "IncidentSummary",
    "IngestResult",
    "Paired",
    "RawRun",
    "Result",
    "Stratum",
    "VerifierReport",
    "canonical_json",
    "conditions_of",
    "digest",
    "engine_from_env",
    "sha256_bytes",
    "sha256_file",
]


def engine_from_env(lock_path: str | Path, *, timeout_s: float = 300.0) -> Engine:
    """Engine configured from ``OPENMHS_BIN`` and ``OPENMHS_BIN_SHA256``.

    When the digest variable is unset, ``<lock dir>/.engine/build.json`` (written by scripts/build-openmhs.sh) is
    used, and only if it names the same binary and the lock's commit. There is no "skip the check" setting.
    """
    lock_path = Path(lock_path)
    binary = os.environ.get("OPENMHS_BIN")
    expected = os.environ.get("OPENMHS_BIN_SHA256")
    build = lock_path.parent / ".engine" / "build.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if build.exists() and (binary is None or expected is None):
        info = json.loads(build.read_text(encoding="utf-8"))
        if info.get("commit") == lock["commit"]:
            binary = binary or info["binary"]
            if Path(binary).resolve() == Path(info["binary"]).resolve():
                expected = expected or info["sha256"]
    if not binary or not expected:
        raise EngineError(
            "engine.binary_missing",
            "set OPENMHS_BIN and OPENMHS_BIN_SHA256, or build the pinned engine with scripts/build-openmhs.sh",
        )
    return Engine(EngineConfig.from_lock(lock_path, binary, expected, timeout_s=timeout_s))
