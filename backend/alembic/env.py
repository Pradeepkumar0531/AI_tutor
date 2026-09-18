"""Alembic environment: reads DATABASE_URL, supports pgvector extension."""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import create_engine

import app.models  # noqa: F401
from alembic import context
from app.db.base import Base  # noqa: F401  (ensures models register here in Phase 2)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    # Shell environment wins (CI explicitness); otherwise fall back to the
    # app Settings, which parse backend/.env robustly (values with & or
    # spaces break naive `source .env`, so never rely on shell sourcing).
    url = os.getenv("DATABASE_URL", "")
    if url:
        return url
    try:
        from app.core.config import get_settings

        return get_settings().database_url
    except Exception:
        return config.get_main_option("sqlalchemy.url") or ""


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()
    if not url:
        # Allow `alembic history/check` without a live database.
        context.configure(url="sqlite://", target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        try:
            connection.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "vector"')
            connection.commit()
        except Exception:  # noqa: BLE001
            # Extension may be unavailable locally; the initial domain migration
            # (0001) also issues CREATE EXTENSION IF NOT EXISTS "vector".
            pass
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
