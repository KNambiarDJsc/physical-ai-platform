"""Alembic environment. The database URL comes from PAP_DATABASE_URL (or -x url=...), never from alembic.ini."""

from __future__ import annotations

import os

from alembic import context
from app.models import Base
from sqlalchemy import create_engine, pool

config = context.config
target_metadata = Base.metadata


def url() -> str:
    x = context.get_x_argument(as_dictionary=True)
    value = x.get("url") or config.attributes.get("url") or os.environ.get("PAP_DATABASE_URL")
    if not value:
        raise RuntimeError("set PAP_DATABASE_URL (or pass -x url=...)")
    return str(value)


def run_offline() -> None:
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
