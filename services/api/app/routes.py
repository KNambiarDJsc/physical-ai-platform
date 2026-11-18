"""All API routers, registered in one place (the isolation test enumerates the app's routes)."""

from __future__ import annotations

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from .evaluations.routes import router as evaluations
    from .evidence.routes import router as evidence
    from .ingestion.routes import router as mappings
    from .organizations.routes import router as organizations
    from .projects.routes import router as projects
    from .releases.routes import router as releases

    for r in (organizations, projects, releases, evidence, mappings, evaluations):
        app.include_router(r)
