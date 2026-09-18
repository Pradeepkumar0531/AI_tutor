"""User + Space + Project repositories (ownership roots of the isolation chain)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import func

from app.models.learning import Project, Space
from app.models.materials import Material
from app.models.users import User
from app.repositories.base import BaseRepository


def escape_like(raw: str) -> str:
    """Escape LIKE wildcards so `search=` is a plain substring match."""
    return raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class UserRepository(BaseRepository[User]):
    model = User

    def create(self, *, email: str, password_hash: str, display_name: str) -> User:
        user = User(
            email=User.normalize_email(email),
            password_hash=password_hash,
            display_name=display_name.strip(),
        )
        return self.add(user)

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(sa.select(User).where(User.email == User.normalize_email(email)))

    def get_active(self, user_id: uuid.UUID) -> User | None:
        return self.session.scalar(
            sa.select(User).where(User.id == user_id, User.is_active.is_(True))
        )


class SpaceRepository(BaseRepository[Space]):
    model = Space

    def create(self, *, owner_id: uuid.UUID, name: str, description: str | None = None) -> Space:
        return self.add(Space(owner_id=owner_id, name=name.strip(), description=description))

    def get_for_user(
        self, space_id: uuid.UUID, user_id: uuid.UUID, *, include_archived: bool = False
    ) -> Space | None:
        stmt = sa.select(Space).where(Space.id == space_id, Space.owner_id == user_id)
        if not include_archived:
            stmt = stmt.where(Space.archived_at.is_(None))
        return self.session.scalar(stmt)

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False,
        search: str | None = None,
    ) -> tuple[list[Space], int]:
        stmt = sa.select(Space).where(Space.owner_id == user_id).order_by(Space.created_at.desc())
        if not include_archived:
            stmt = stmt.where(Space.archived_at.is_(None))
        if search and search.strip():
            stmt = stmt.where(Space.name.ilike(f"%{escape_like(search.strip())}%", escape="\\"))
        return self.paginate(stmt, page=page, page_size=page_size)

    def count_projects_for_spaces(
        self, user_id: uuid.UUID, space_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """One GROUP BY query for a page of spaces — never one query per card."""
        if not space_ids:
            return {}
        rows = self.session.execute(
            sa.select(Project.space_id, func.count(Project.id))
            .where(
                Project.space_id.in_(space_ids),
                Project.owner_id == user_id,
                Project.archived_at.is_(None),
            )
            .group_by(Project.space_id)
        ).all()
        return {space_id: count for space_id, count in rows}


class ProjectRepository(BaseRepository[Project]):
    model = Project

    def create(
        self,
        *,
        space_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
        description: str | None = None,
        learning_goal: str | None = None,
    ) -> Project:
        return self.add(
            Project(
                space_id=space_id,
                owner_id=owner_id,
                name=name.strip(),
                description=description,
                learning_goal=learning_goal,
            )
        )

    def get_for_user(
        self, project_id: uuid.UUID, user_id: uuid.UUID, *, include_archived: bool = False
    ) -> Project | None:
        """Scoped root lookup: every downstream scoped accessor starts here."""
        stmt = sa.select(Project).where(Project.id == project_id, Project.owner_id == user_id)
        if not include_archived:
            stmt = stmt.where(Project.archived_at.is_(None))
        return self.session.scalar(stmt)

    def list_for_space(
        self,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False,
        search: str | None = None,
    ) -> tuple[list[Project], int]:
        stmt = (
            sa.select(Project)
            .where(Project.space_id == space_id, Project.owner_id == user_id)
            .order_by(Project.created_at.desc())
        )
        if not include_archived:
            stmt = stmt.where(Project.archived_at.is_(None))
        if search and search.strip():
            stmt = stmt.where(Project.name.ilike(f"%{escape_like(search.strip())}%", escape="\\"))
        return self.paginate(stmt, page=page, page_size=page_size)

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False,
        search: str | None = None,
    ) -> tuple[list[Project], int]:
        stmt = (
            sa.select(Project)
            .where(Project.owner_id == user_id)
            .order_by(Project.created_at.desc())
        )
        if not include_archived:
            stmt = stmt.where(Project.archived_at.is_(None))
        if search and search.strip():
            stmt = stmt.where(Project.name.ilike(f"%{escape_like(search.strip())}%", escape="\\"))
        return self.paginate(stmt, page=page, page_size=page_size)

    def count_materials_for_projects(
        self, project_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """One GROUP BY query for a page of projects — never one query per card."""
        if not project_ids:
            return {}
        rows = self.session.execute(
            sa.select(Material.project_id, func.count(Material.id))
            .where(Material.project_id.in_(project_ids), Material.archived_at.is_(None))
            .group_by(Material.project_id)
        ).all()
        return {project_id: count for project_id, count in rows}
