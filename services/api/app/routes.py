"""All API routers, registered in one place (the isolation test enumerates the app's routes)."""

from __future__ import annotations

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from .evaluations.routes import router as evaluations
    from .evidence.routes import router as evidence
    from .hardware.routes import router as hardware
    from .ingestion.routes import router as mappings
    from .organizations.routes import router as organizations
    from .projects.routes import router as projects
    from .releases.routes import router as releases
    from .workflows.routes import router as workflows

    for r in (organizations, projects, releases, evidence, mappings, evaluations, hardware, workflows):
        app.include_router(r)
