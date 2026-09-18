"""Shared persistence fixtures.

SQLite stands in for PostgreSQL (no DATABASE_URL in CI/dev here): the models use
portable column types (``sa.Uuid``, ``sa.Enum``, JSON-with-variant) so the same
metadata creates cleanly on both. Foreign keys are enforced via PRAGMA so cascade
and composite-FK behavior is actually tested. Postgres-specific rendering
(Vector, JSONB, native enums) is covered separately in test_pg_dialect.py.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all tables)
from app.core.security import hash_password
from app.db.base import Base
from app.models.learning import Project, Space
from app.models.users import User


@pytest.fixture(scope="session")
def engine() -> sa.Engine:
    eng = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(eng, "connect")
    def _enforce_fk(dbapi_conn, _conn_record) -> None:  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine: sa.Engine) -> Session:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = factory()
    yield s
    s.rollback()
    s.close()
    cleanup = factory()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            cleanup.execute(table.delete())
        cleanup.commit()
    finally:
        cleanup.close()


def make_user(session: Session, email: str | None = None, display_name: str = "Test User") -> User:
    from app.repositories.projects import UserRepository

    user = UserRepository(session).create(
        email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password-123"),
        display_name=display_name,
    )
    session.commit()
    return user


def make_space(session: Session, owner: User, name: str = "Test Space") -> Space:
    from app.repositories.projects import SpaceRepository

    space = SpaceRepository(session).create(owner_id=owner.id, name=name)
    session.commit()
    return space


def make_project(
    session: Session, owner: User, space: Space | None = None, name: str = "Test Project"
) -> Project:
    from app.services.project_service import ProjectService

    space = space or make_space(session, owner)
    return ProjectService(session).create_project(user_id=owner.id, space_id=space.id, name=name)
