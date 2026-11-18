"""OBS-001 (application side): JSON logs with request and job ids, metrics, and one trace from API request through the
evaluation job to every engine invocation. Real API, real worker code, real engine."""

from __future__ import annotations

import io
import json
import logging
import re
from collections.abc import Iterator
from typing import Any

import pytest
from conftest import DEMO
from fastapi.testclient import TestClient
from helpers import as_user
from test_jobs import P, work_once

SUBMIT_ROUTE = "/api/v1/orgs/{org_slug}/projects/{project_slug}/evaluations"


@pytest.fixture
def spans(client: TestClient) -> Iterator[Any]:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider), "create_app installs the SDK tracer provider"
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter
    exporter.clear()


@pytest.fixture
def logs(client: TestClient) -> Iterator[io.StringIO]:
    from app.observability import JsonFormatter

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter("test"))
    root = logging.getLogger()
    root.addHandler(handler)
    yield buf
    root.removeHandler(handler)


@pytest.mark.engine
def test_one_trace_from_request_to_engine_with_json_logs(
    client: TestClient, demo: dict[str, Any], omhs: Any, spans: Any, logs: io.StringIO
) -> None:
    r = client.post(f"{P}/evaluations", json=demo["body"], headers={**as_user("alice"), "X-Request-ID": "req-obs-1"})
    assert r.status_code == 201, r.text
    assert r.headers["x-request-id"] == "req-obs-1"
    job_id = r.json()["id"]
    assert work_once() == "succeeded"

    finished = spans.get_finished_spans()
    request = [s for s in finished if s.name == f"POST {SUBMIT_ROUTE}"][-1]
    assert request.attributes["http.response.status_code"] == 201
    assert request.attributes["pap.request_id"] == "req-obs-1"
    job = next(s for s in finished if s.name == "evaluation.job" and s.attributes["pap.job.id"] == job_id)
    # The worker continued the submitting request's trace from the context stored with the job.
    assert job.context.trace_id == request.context.trace_id
    assert job.parent is not None and job.parent.span_id == request.context.span_id
    assert job.attributes["pap.job.outcome"] == "succeeded"
    engine = [s for s in finished if s.name.startswith("engine ") and s.context.trace_id == request.context.trace_id]
    names = {s.name for s in engine}
    assert {"engine outcome verify", "engine ops ingest", "engine ops compare", "engine ops incidents"} <= names
    assert all(s.parent is not None and s.parent.span_id == job.context.span_id for s in engine)
    assert sum(s.name == "engine outcome verify" for s in engine) >= 200  # one verifier run per episode
    assert all(s.attributes["pap.engine.outcome"] == "ok" for s in engine)
    for s in engine:  # no paths, arguments or evidence in span attributes
        assert not any(isinstance(v, str) and ("/" in v or "\\" in v) for v in s.attributes.values()), s.attributes

    text = logs.getvalue()
    lines = [json.loads(line) for line in text.splitlines()]  # every line is one JSON object
    req_log = [x for x in lines if x.get("event") == "request" and x.get("request_id") == "req-obs-1"]
    assert req_log and req_log[0]["route"] == SUBMIT_ROUTE and req_log[0]["status"] == 201
    assert req_log[0]["trace_id"] == format(request.context.trace_id, "032x")
    job_logs = [x for x in lines if x.get("job_id") == job_id]
    done = [x for x in job_logs if x.get("event") == "job"]
    assert done and done[0]["state"] == "succeeded"
    assert all(x["trace_id"] == format(request.context.trace_id, "032x") for x in job_logs)
    # Never credentials, never uploaded content.
    assert "Bearer" not in text and "dev:alice" not in text
    for fragment in ("bin_mass_delta_g", "base-0001", "sku-mug@shelf-a1", "operator_assist"):
        assert fragment in (DEMO / "data" / "baseline.csv").read_text(encoding="utf-8")
        assert fragment not in text, fragment


@pytest.mark.engine
def test_metrics(client: TestClient, demo: dict[str, Any], omhs: Any) -> None:
    job = client.post(f"{P}/evaluations", json=demo["body"], headers=as_user("alice")).json()
    assert work_once() == "succeeded"
    r = client.get("/metrics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    text = r.text
    assert 'pap_evaluation_jobs{state="succeeded"} 1.0' in text
    assert 'pap_evaluation_jobs{state="queued"} 0.0' in text
    route = re.escape(SUBMIT_ROUTE)
    assert re.search(
        rf'pap_http_request_duration_seconds_count\{{method="POST",route="{route}",status="201"\}} [1-9]', text
    )
    assert re.search(r'pap_engine_invocations_total\{command="ops compare",result="ok"\} [1-9]', text)
    assert re.search(r'pap_evaluation_job_duration_seconds_count\{outcome="succeeded"\} [1-9]', text)
    assert "acme" not in text and job["id"] not in text  # no tenant names or ids in metric labels


def test_engine_failures_are_counted_and_marked_in_traces() -> None:
    from app.observability import engine_observer
    from openmhs_bridge import Invocation
    from prometheus_client import REGISTRY

    labels = {"command": "ops compare", "code": "engine.timeout"}
    before = REGISTRY.get_sample_value("pap_engine_failures_total", labels) or 0.0
    engine_observer(Invocation("ops compare", 1_000, 2_000, None, "engine.timeout"))
    assert REGISTRY.get_sample_value("pap_engine_failures_total", labels) == before + 1


def test_log_lines_are_json_and_secrets_are_redacted() -> None:
    from app.observability import JsonFormatter

    msg = (
        'a "quoted" value; Authorization: Bearer abc.def.ghi; jwt eyJhbGciOiJSUzI1.eyJzdWIiOiJ4In0.c2ln; pap_svc_XyZ123'
    )
    record = logging.LogRecord("pap.test", logging.INFO, __file__, 1, msg, None, None)
    doc = json.loads(JsonFormatter("test").format(record))
    assert '"quoted"' in doc["msg"]
    for secret in ("abc.def.ghi", "eyJhbGciOiJSUzI1", "pap_svc_XyZ123"):
        assert secret not in doc["msg"]


def test_request_ids_are_validated(client: TestClient) -> None:
    good = client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert good.headers["x-request-id"] == "abc-123"
    bad = client.get("/healthz", headers={"X-Request-ID": "x" * 65 + " <script>"})
    assert re.fullmatch(r"[0-9a-f]{32}", bad.headers["x-request-id"])


def test_metrics_are_closed_in_production(settings_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("PAP_ENV", "production")
    monkeypatch.setenv("PAP_AUTH_MODE", "oidc")
    monkeypatch.setenv("PAP_OIDC_ISSUER", "https://idp.example/realms/pap")
    monkeypatch.setenv("PAP_OIDC_AUDIENCE", "pap-api")
    get_settings.cache_clear()
    try:
        assert TestClient(create_app()).get("/metrics").status_code == 404
        monkeypatch.setenv("PAP_METRICS_TOKEN", "metrics-secret-for-test")
        get_settings.cache_clear()
        c = TestClient(create_app())
        assert c.get("/metrics").status_code == 401
        assert c.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/metrics", headers={"Authorization": "Bearer metrics-secret-for-test"}).status_code == 200
    finally:
        get_settings.cache_clear()
