from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from openmhs_bridge import Engine, EngineError, engine_from_env

ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT / "engine.lock.json"


def _unavailable(reason: str) -> None:
    if os.environ.get("PAP_REQUIRE_ENGINE") == "1":
        pytest.fail(f"PAP_REQUIRE_ENGINE=1 but {reason}")
    pytest.skip(reason)


@pytest.fixture(scope="session")
def engine() -> Engine:
    try:
        e = engine_from_env(LOCK)
        e.check_binary()
    except EngineError as err:
        _unavailable(f"pinned engine unavailable: {err}")
    return e


@pytest.fixture(scope="session")
def pinned_src() -> Path:
    commit = json.loads(LOCK.read_text(encoding="utf-8"))["commit"]
    src = ROOT / ".engine" / f"src-{commit}"
    if not (src / "Cargo.lock").exists():
        _unavailable(f"pinned source tree {src} not exported (run scripts/build-openmhs.sh)")
    return src


@pytest.fixture(scope="session")
def fixtures(pinned_src: Path) -> Path:
    return pinned_src / "crates" / "openmhs-ops" / "tests" / "fixtures"
