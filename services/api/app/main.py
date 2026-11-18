"""FastAPI application. The evaluation worker is a separate process (``python -m app.workers.run``)."""

from __future__ import annotations

import hmac
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from opentelemetry.trace import SpanKind, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from sqlalchemy import text

from .config import get_settings
from .db import get_engine
from .engine import engine_status
from .observability import (
    HTTP_SECONDS,
    REQUEST_ID,
    configure_logging,
    configure_tracing,
    extract_context,
    monotonic_ms,
    register_job_state_collector,
    request_id_var,
    tracer,
)

log = logging.getLogger("pap.api")

API_VERSION = "0.1.0"


def create_app() -> FastAPI:
    settings = get_settings()  # validates configuration at start: unsafe combinations refuse to start
    configure_logging("pap-api")
    configure_tracing("pap-api")
    register_job_state_collector()
    app = FastAPI(
        title="Physical AI Reliability Platform API",
        version=API_VERSION,
        docs_url="/api/docs" if settings.env != "production" else None,
        openapi_url="/api/openapi.json",
        # FastAPI's built-in telemetry records concrete URL paths (tenant slugs, ids); the `observe` middleware below
        # makes the one request span, with the route template only (D-020).
        telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False},
    )

    @app.get("/healthz", tags=["health"])
    def healthz() -> JSONResponse:
        db: dict[str, Any]
        try:
            with get_engine().connect() as conn:
                version = conn.execute(text("show server_version")).scalar_one()
                rev = conn.execute(text("select version_num from alembic_version")).scalar_one_or_none()
            db = {"ok": True, "server_version": version, "schema_revision": rev}
        except Exception as e:  # noqa: BLE001  health must report any database failure, not raise
            db = {"ok": False, "error": type(e).__name__}
        eng = engine_status()
        ok = db["ok"] and eng["ok"]
        body = {"status": "ok" if ok else "degraded", "api_version": API_VERSION, "database": db, "engine": eng}
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.middleware("http")
    async def observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Request id, one server span and one log line per request, and the request-duration metric."""
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            ctx = extract_context(dict(request.headers))
            with tracer.start_as_current_span(request.method, context=ctx, kind=SpanKind.SERVER) as span:
                try:
                    response = await call_next(request)
                    status = response.status_code
                finally:
                    route = getattr(request.scope.get("route"), "path", "unmatched")
                    span.update_name(f"{request.method} {route}")
                    span.set_attribute("http.request.method", request.method)
                    span.set_attribute("http.route", route)
                    span.set_attribute("http.response.status_code", status)
                    span.set_attribute("pap.request_id", rid)
                    if status >= 500:
                        span.set_status(StatusCode.ERROR)
                    HTTP_SECONDS.labels(request.method, route, str(status)).observe(time.perf_counter() - start)
                    fields = {"method": request.method, "route": route, "status": status}
                    log.info("request", extra={"event": "request", **fields, "duration_ms": monotonic_ms(start)})
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_var.reset(token)

    @app.get("/metrics", tags=["health"], response_class=Response, responses={200: {"content": {"text/plain": {}}}})
    def metrics(request: Request) -> Response:
        """Prometheus metrics. Open outside production; in production only with PAP_METRICS_TOKEN, else 404."""
        expected = settings.metrics_token
        if expected:
            given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(given.encode(), expected.encode()):
                return JSONResponse({"detail": {"code": "unauthorized", "message": "metrics token required"}}, 401)
        elif settings.env == "production":
            return JSONResponse({"detail": {"code": "not_found", "message": "not found"}}, 404)
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    from .routes import register

    register(app)
    return app
