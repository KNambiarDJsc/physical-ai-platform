"""All API routers, registered in one place (the isolation test enumerates the app's routes)."""

from __future__ import annotations

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from .organizations.routes import router as organizations
    from .projects.routes import router as projects

    app.include_router(organizations)
    app.include_router(projects)
