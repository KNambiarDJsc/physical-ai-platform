"""RI-002: a worker PROCESS is killed (no cleanup) while running a job; another worker recovers and finishes it."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import as_user, ok
from test_jobs import P

API = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.engine


def state(job_id: str) -> tuple[str, str | None, int]:
    from app.db import session_factory
    from app.evaluations.models import EvaluationJob

    with session_factory()() as s:
        j = s.get(EvaluationJob, job_id)
        assert j is not None
        return j.state, j.lease_owner, j.attempts


def test_killed_worker_is_recovered(client: TestClient, demo: dict[str, Any]) -> None:
    from app.config import get_settings
    from app.workers.run import run

    job = ok(client.post(f"{P}/evaluations", json=demo["body"], headers=as_user("alice")), 201)
    env = {**os.environ, "PYTHONPATH": str(API)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.workers.run", "--once"],
        cwd=API,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 60
        while state(job["id"])[0] != "running":
            assert proc.poll() is None, "worker exited before claiming the job"
            assert time.monotonic() < deadline, "worker never claimed the job"
            time.sleep(0.1)
        time.sleep(1.0)  # let it get into the engine work
    finally:
        proc.kill()  # hard kill: TerminateProcess / SIGKILL, no cleanup handlers run
        proc.wait()
    st, owner, attempts = state(job["id"])
    assert (st, attempts) == ("running", 1) and owner is not None  # orphaned with a lease

    # A fresh worker waits for the lease to expire, re-queues the job and completes it.
    time.sleep(get_settings().worker_lease_s + 1)
    run(once=True, poll_s=0.2)
    st, owner, attempts = state(job["id"])
    assert (st, owner, attempts) == ("succeeded", None, 2)
    cmp_ = ok(client.get(f"{P}/evaluations/{job['id']}/comparison", headers=as_user("alice")))
    assert cmp_["verified"]["result"]["b"]["attempt_outcomes"] == [77, 34, 9]  # same answer as an uninterrupted run


def test_lost_worker_cannot_write_after_recovery(client: TestClient, demo: dict[str, Any]) -> None:
    """A worker whose lease was taken over must not persist anything (results are lease-guarded)."""
    from app.db import session_factory
    from app.engine import get_engine
    from app.evaluations import service
    from app.evaluations.models import EvaluationResult
    from app.evaluations.pipeline import run_pipeline
    from app.evidence.storage import get_storage
    from sqlalchemy import func, select, text

    job = ok(client.post(f"{P}/evaluations", json=demo["body"], headers=as_user("alice")), 201)
    with session_factory()() as s:
        assert service.claim(s, "slow-worker", 5) is not None
        job_row = s.get(service.EvaluationJob, job["id"])
        assert job_row is not None
        inp = service.load_input(s, job_row, get_storage())
        s.execute(text("UPDATE evaluation_jobs SET lease_expires_at = now() - interval '1 second'"))
        s.commit()
        assert service.recover_expired(s) == 1
        assert service.claim(s, "new-worker", 5) is not None
    out = run_pipeline(get_engine(), inp, Path(get_settings_work()) / "slow")
    with session_factory()() as s:
        assert service.persist_success(s, job["id"], "slow-worker", out, get_storage()) is False
        assert s.scalar(select(func.count()).select_from(EvaluationResult)) == 0


def get_settings_work() -> Path:
    from app.config import get_settings

    return get_settings().work_path
