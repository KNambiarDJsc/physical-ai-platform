"""The evaluation worker: a separate process that claims queued jobs and runs them with the pinned engine.

    python -m app.workers.run            # run until stopped
    python -m app.workers.run --once     # process at most one job, then exit (tests, cron)

Never runs inside the API. Holds a lease per job and renews it from a heartbeat thread; the heartbeat also notices a
cancellation request or the job deadline and kills the engine process through the cancel event.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import socket
import threading
import time
import uuid
from typing import Any

from openmhs_bridge import EngineError
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import update

from ..config import get_settings
from ..db import session_factory
from ..engine import get_engine
from ..evaluations import service
from ..evaluations.models import EvaluationJob
from ..evaluations.pipeline import PipelineError, run_pipeline
from ..evidence.storage import get_storage
from ..observability import (
    JOB_SECONDS,
    configure_logging,
    configure_tracing,
    extract_context,
    job_id_var,
    tracer,
)
from ..workflows import service as wf_service
from ..workflows.executor import execute_run

log = logging.getLogger("pap.worker")


class _Watch(threading.Thread):
    """Renews the lease; sets ``cancel`` on a cancellation request, a lost lease or the deadline."""

    def __init__(self, job_id: uuid.UUID, worker: str, lease_s: int, deadline: float) -> None:
        super().__init__(daemon=True)
        self.job_id, self.worker, self.lease_s, self.deadline = job_id, worker, lease_s, deadline
        self.cancel = threading.Event()
        self.stop = threading.Event()
        self.reason: str | None = None
        self._lock = threading.Lock()

    def check(self) -> str | None:
        """Renew the lease and look for a reason to stop. Called at once, on every interval, and once more before
        results are saved: a job can finish inside one interval, and a cancellation or an exceeded deadline must
        still win (found by CI, where the whole run fitted inside the first interval)."""
        with self._lock:
            if self.reason is None:
                with session_factory()() as s:
                    owner, cancel_requested = service.heartbeat(s, self.job_id, self.worker, self.lease_s)
                if not owner:
                    self.reason = "lease_lost"
                elif cancel_requested:
                    self.reason = "cancelled"
                elif time.monotonic() > self.deadline:
                    self.reason = "timeout"
                if self.reason:
                    self.cancel.set()
            return self.reason

    def run(self) -> None:
        interval = max(1.0, self.lease_s / 3)
        self.check()
        while self.reason is None and not self.stop.wait(interval):
            self.check()


def service_cancel_requested(job_id: uuid.UUID) -> bool:
    with session_factory()() as s:
        job = s.get(EvaluationJob, job_id)
        return bool(job and job.cancel_requested)


def execute(job_id: uuid.UUID, worker: str) -> str:
    """Run one claimed job inside a span that continues the submitting request's trace."""
    with session_factory()() as s:
        job = s.get(EvaluationJob, job_id)
        carrier = job.trace_context if job else None
        attempt = job.attempts if job else 0
    token = job_id_var.set(str(job_id))
    start = time.perf_counter()
    state = "failed"
    try:
        with tracer.start_as_current_span(
            "evaluation.job",
            context=extract_context(carrier),
            kind=SpanKind.CONSUMER,
            attributes={"pap.job.id": str(job_id), "pap.job.attempt": attempt},
        ) as span:
            try:
                state = _execute(job_id, worker)
            finally:
                span.set_attribute("pap.job.outcome", state)
                if state not in ("succeeded", "cancelled"):
                    span.set_status(StatusCode.ERROR, state)
                JOB_SECONDS.labels(state).observe(time.perf_counter() - start)
                log.info("job finished", extra={"event": "job", "state": state, "attempt": attempt})
        return state
    finally:
        job_id_var.reset(token)


def _execute(job_id: uuid.UUID, worker: str) -> str:
    settings = get_settings()
    storage = get_storage()
    with session_factory()() as s:
        job = s.get(EvaluationJob, job_id)
        assert job is not None
        timeout_s, attempts, max_attempts = job.timeout_s, job.attempts, job.max_attempts
    watch = _Watch(job_id, worker, settings.worker_lease_s, time.monotonic() + timeout_s)
    watch.start()
    workdir = settings.work_path / str(job_id)
    try:
        with session_factory()() as s:
            job = s.get(EvaluationJob, job_id)
            assert job is not None
            inp = service.load_input(s, job, storage)
        out = run_pipeline(get_engine(), inp, workdir, cancel=watch.cancel)
        if watch.check():  # cancelled, timed out or lost the lease while the last stage ran: do not save
            raise PipelineError(f"job.{watch.reason}", f"stopped before the results were saved: {watch.reason}")
        with session_factory()() as s:
            ok = service.persist_success(s, job_id, worker, out, storage)
        if ok:
            return "succeeded"
        if watch.reason is None and service_cancel_requested(job_id):
            watch.reason = "cancelled"  # requested between the last check and the save, which refused it
            raise PipelineError("job.cancelled", "cancelled before the results were saved")
        return "lease_lost"
    except (PipelineError, EngineError) as e:
        err: dict[str, Any] = e.to_dict()
        if watch.reason == "cancelled":
            state, err_out = "cancelled", None
        elif watch.reason == "lease_lost":
            return "lease_lost"
        elif watch.reason == "timeout":
            state = "queued" if attempts < max_attempts else "failed"
            err_out = {"code": "job.timeout", "message": f"exceeded {timeout_s} s", "transient": True, "detail": {}}
        else:
            state = "queued" if e.transient and attempts < max_attempts else "failed"
            err_out = err
        with session_factory()() as s:
            if state == "queued":
                s.execute(
                    update(EvaluationJob)
                    .where(EvaluationJob.id == job_id, EvaluationJob.lease_owner == worker)
                    .values(state="queued", error=err_out, lease_owner=None, lease_expires_at=None)
                )
                s.commit()
            else:
                service.finish(s, job_id, worker, state, err_out)
        return state
    except Exception as e:
        log.exception("job %s failed unexpectedly", job_id)
        with session_factory()() as s:
            service.finish(
                s, job_id, worker, "failed", {"code": "job.internal", "message": type(e).__name__, "transient": False}
            )
        return "failed"
    finally:
        watch.stop.set()
        shutil.rmtree(workdir, ignore_errors=True)


def run(once: bool = False, poll_s: float = 1.0) -> None:
    settings = get_settings()
    worker = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    get_engine().check_binary()  # refuse to start with the wrong engine
    last_recovery = 0.0
    while True:
        if time.monotonic() - last_recovery > settings.worker_lease_s / 2:
            with session_factory()() as s:
                n = service.recover_expired(s) + wf_service.recover_expired(s)
            if n:
                log.warning("recovered %d job(s) whose worker stopped", n)
            last_recovery = time.monotonic()
        with session_factory()() as s:
            job_id = service.claim(s, worker, settings.worker_lease_s)
        if job_id is None:
            with session_factory()() as s:
                run_id = wf_service.claim(s, worker, settings.worker_lease_s)
            if run_id is not None:
                log.info("workflow run %s claimed by %s", run_id, worker)
                execute_run(run_id, worker)
                if once:
                    return
                continue
            if once:
                return
            time.sleep(poll_s)
            continue
        log.info("job %s claimed by %s", job_id, worker)
        execute(job_id, worker)
        if once:
            return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll", type=float, default=1.0)
    ns = ap.parse_args()
    configure_logging("pap-worker")
    configure_tracing("pap-worker")
    port = get_settings().worker_metrics_port
    if port:
        from prometheus_client import start_http_server

        start_http_server(port)  # job durations and engine metrics are recorded in this process
    run(once=ns.once, poll_s=ns.poll)


if __name__ == "__main__":
    main()
