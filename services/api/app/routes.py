"""All API routers, registered in one place (the isolation test enumerates the app's routes)."""

from __future__ import annotations

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    """Routers are added here as features land."""
    return None
