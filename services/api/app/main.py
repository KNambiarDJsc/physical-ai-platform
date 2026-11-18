"""FastAPI application. The evaluation worker is a separate process (``python -m app.workers.run``)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .db import get_engine
from .engine import engine_status

API_VERSION = "0.1.0"


def create_app() -> FastAPI:
    settings = get_settings()  # validates configuration at start: unsafe combinations refuse to start
    app = FastAPI(
        title="Physical AI Reliability Platform API",
        version=API_VERSION,
        docs_url="/api/docs" if settings.env != "production" else None,
        openapi_url="/api/openapi.json",
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

    from .routes import register

    register(app)
    return app
