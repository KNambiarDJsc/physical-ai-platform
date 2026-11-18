"""Operational observability (OBS-001): JSON logs, Prometheus metrics and OpenTelemetry traces.

What is recorded is operational only: ids, routes (as templates), status codes, durations, job states and engine
outcome codes. Never request bodies, uploaded evidence, engine output or credentials; anything that looks like a
bearer token or a JWT is redacted from log messages as a second line of defence.

Traces span API request -> evaluation job -> engine invocation. The job runs in another process, so the
submitting request's trace context is stored with the job (``evaluation_jobs.trace_context``) and the worker
continues the trace from it. Spans are exported only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or the traces-specific
variable) is set; otherwise they are created and dropped.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from collections.abc import Iterator
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from openmhs_bridge import Invocation
from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode
from prometheus_client import REGISTRY, Counter, Histogram
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

request_id_var: ContextVar[str | None] = ContextVar("pap_request_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("pap_job_id", default=None)
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# --- logs ----------------------------------------------------------------------------------------------------------

_SECRET = re.compile(r"(?i)\b(bearer\s+)\S+|\beyJ[\w-]{6,}\.[\w-]{6,}\.[\w-]*|\bpap_svc_\S+")
_FIELDS = ("event", "method", "route", "status", "duration_ms", "state", "code", "command", "outcome", "attempt")


def redact(text: str) -> str:
    return _SECRET.sub(lambda m: f"{m.group(1) or ''}[redacted]", text)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the request and job ids of the current context."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if rid := request_id_var.get():
            doc["request_id"] = rid
        if jid := job_id_var.get():
            doc["job_id"] = jid
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            doc["trace_id"] = format(ctx.trace_id, "032x")
            doc["span_id"] = format(ctx.span_id, "016x")
        for k in _FIELDS:
            if k in record.__dict__:
                doc[k] = record.__dict__[k]
        if record.exc_info and record.exc_info[0] is not None:
            doc["exc_type"] = record.exc_info[0].__name__
            doc["exc"] = redact(self.formatException(record.exc_info))[-4000:]
        return json.dumps(doc, ensure_ascii=False, default=str)


class _StderrHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Writes to whatever sys.stderr is at the time of the write (process managers and test runners swap it)."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def stream(self) -> Any:
        return sys.stderr

    @stream.setter
    def stream(self, _value: Any) -> None:
        pass


def configure_logging(service: str, level: int = logging.INFO) -> None:
    root = logging.getLogger()
    handler = _StderrHandler()
    handler.setFormatter(JsonFormatter(service))
    # Replace only our own handler (calling this twice must not duplicate lines; test harness handlers stay).
    root.handlers = [h for h in root.handlers if not isinstance(h, _StderrHandler)] + [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").disabled = True  # the request log below replaces it


# --- traces --------------------------------------------------------------------------------------------------------


def configure_tracing(service: str) -> TracerProvider:
    """Install the process's tracer provider once. Exports over OTLP/HTTP only when an endpoint is configured."""
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return current
    provider = TracerProvider(resource=Resource.create({"service.name": service, "service.namespace": "pap"}))
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider


tracer = trace.get_tracer("pap")


def inject_context() -> dict[str, str]:
    """The current trace context as W3C headers, to store with a job."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier


def extract_context(carrier: dict[str, str] | None) -> Context:
    return propagate.extract(carrier or {})


# --- metrics -------------------------------------------------------------------------------------------------------

HTTP_SECONDS = Histogram("pap_http_request_duration_seconds", "API request duration", ["method", "route", "status"])
JOB_SECONDS = Histogram(
    "pap_evaluation_job_duration_seconds",
    "Evaluation job duration in the worker, by outcome",
    ["outcome"],
    buckets=(1, 2.5, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600),
)
ENGINE_SECONDS = Histogram(
    "pap_engine_invocation_duration_seconds",
    "OpenMHS engine process duration",
    ["command"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300),
)
ENGINE_RUNS = Counter("pap_engine_invocations", "OpenMHS engine processes, by result", ["command", "result"])
ENGINE_FAILURES = Counter(
    "pap_engine_failures", "OpenMHS engine processes that failed, by error code", ["command", "code"]
)


def engine_observer(inv: Invocation) -> None:
    """Bridge observer: one metric sample and one span per engine process (child of the current span)."""
    ok = inv.outcome == "ok"
    ENGINE_SECONDS.labels(inv.command).observe(max(0, inv.end_ns - inv.start_ns) / 1e9)
    ENGINE_RUNS.labels(inv.command, "ok" if ok else "failed").inc()
    if not ok:
        ENGINE_FAILURES.labels(inv.command, inv.outcome).inc()
    attrs: dict[str, Any] = {"pap.engine.command": inv.command, "pap.engine.outcome": inv.outcome}
    if inv.returncode is not None:
        attrs["process.exit.code"] = inv.returncode
    span = tracer.start_span(f"engine {inv.command}", start_time=inv.start_ns, attributes=attrs)
    if not ok:
        span.set_status(Status(StatusCode.ERROR, inv.outcome))
    span.end(end_time=inv.end_ns)


class JobStateCollector(Collector):
    """Job counts by state, read from the database at scrape time (correct across API and worker processes)."""

    def collect(self) -> Iterator[GaugeMetricFamily]:
        from sqlalchemy import func, select

        from ..db import session_factory
        from ..evaluations.models import STATES, EvaluationJob

        g = GaugeMetricFamily("pap_evaluation_jobs", "Evaluation jobs by state", labels=["state"])
        try:
            with session_factory()() as s:
                q = select(EvaluationJob.state, func.count()).group_by(EvaluationJob.state)
                counts: dict[str, int] = {state: n for state, n in s.execute(q)}
        except Exception:  # noqa: BLE001  a scrape must not fail the API; the gauge is simply absent
            return
        for state in STATES:
            g.add_metric([state], float(counts.get(state, 0)))
        yield g


_collector_registered = False


def register_job_state_collector() -> None:
    global _collector_registered
    if not _collector_registered:
        REGISTRY.register(JobStateCollector())
        _collector_registered = True


def monotonic_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
