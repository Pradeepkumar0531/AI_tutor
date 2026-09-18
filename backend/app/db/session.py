"""Engine + session management. Safe when DATABASE_URL is not configured."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine = None
_session_factory: sessionmaker | None = None


def _build_engine() -> Any | None:
    settings = get_settings()
    if not settings.database_url:
        return None
    # Future: pgvector lives in the same Postgres; no second database.
    # Pool knobs are settings (modest dev defaults; raise for production).
    kwargs: dict = {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
        "pool_recycle": settings.db_pool_recycle_seconds,
    }
    # Same pool for SQLite: fewer pooled connections do NOT serialize SQLite
    # writes (the file lock does that) — they only queue checkouts under
    # concurrent load (E2E runs fully parallel against SQLite). Verified by
    # the Playwright suite; do not special-case this without re-running it.
    return create_engine(settings.database_url, **kwargs)


def get_engine() -> Any | None:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> sessionmaker | None:
    global _session_factory
    engine = get_engine()
    if engine is None:
        return None
    if _session_factory is None:
        _session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency. Yields a session with explicit commit/rollback boundary."""
    factory = get_session_factory()
    if factory is None:
        # Database not configured: yield nothing and let readiness report degraded.
        raise RuntimeError("DATABASE_URL is not configured")
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database() -> dict:
    engine = get_engine()
    if engine is None:
        return {"configured": False, "reachable": False}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"configured": True, "reachable": True}
    except Exception as e:  # noqa: BLE001
        return {"configured": True, "reachable": False, "error": type(e).__name__}


def reset_engine_cache() -> None:
    global _engine, _session_factory
    _engine = None
    _session_factory = None
