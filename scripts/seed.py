#!/usr/bin/env python3
"""Development-only seed: one demo user + space + project + concept.

Clearly labeled dev data — never run against production. Requires DATABASE_URL.
Usage:  cd backend && .venv/bin/python ../scripts/seed.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.repositories.knowledge import ConceptRepository  # noqa: E402
from app.repositories.projects import UserRepository  # noqa: E402
from app.services.project_service import ProjectService  # noqa: E402


def main() -> None:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is not set — seed needs a real PostgreSQL.")
    if "prod" in url:
        raise SystemExit("Refusing to seed what looks like a production database.")

    engine = create_engine(url)
    Base.metadata.create_all(engine)  # dev convenience; real deploys use alembic
    session = sessionmaker(bind=engine)()

    user = UserRepository(session).create(
        email="dev@example.com",
        password_hash=hash_password("dev-password-123"),
        display_name="Dev User",
    )
    session.flush()
    projects = ProjectService(session)
    space = projects.create_space(
        owner_id=user.id, name="Dev Space", description="DEV SEED — delete me"
    )
    session.flush()
    project = projects.create_project(
        user_id=user.id, space_id=space.id, name="Dev Project"
    )
    ConceptRepository(session).get_or_create(
        project_id=project.id, name="Dev Concept", description="DEV SEED — delete me"
    )
    session.commit()
    print(f"seeded dev user={user.id} space={space.id} project={project.id}")


if __name__ == "__main__":
    main()
