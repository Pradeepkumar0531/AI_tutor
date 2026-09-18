"""Project service: ownership-consistent creation of spaces/projects.

``owner_id`` is denormalized on Project for O(1) authorization; this service is the
only writer that sets it, always copying the Space owner's id.

Deletion policy: no hard deletes. Archive sets ``archived_at`` (reversible via
restore); every row stays in place so future Materials/Documents/Chunks/Concepts/
Quizzes/Attempts/Mastery attached to a project can never be orphaned by a click.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.enums import Difficulty, EventType
from app.models.learning import Project, Space
from app.models.mixins import utcnow
from app.repositories.intelligence import EventRepository
from app.repositories.projects import ProjectRepository, SpaceRepository
from app.services.base import BaseService, transactional


class ProjectService(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.spaces = SpaceRepository(session)
        self.projects = ProjectRepository(session)
        self.events = EventRepository(session)

    @transactional
    def create_space(
        self, *, owner_id: uuid.UUID, name: str, description: str | None = None
    ) -> Space:
        space = self.spaces.create(owner_id=owner_id, name=name, description=description)
        self.session.flush()  # id needed for the event row below
        self.events.append(
            event_type=EventType.SPACE_CREATED,
            user_id=owner_id,
            entity_type="space",
            entity_id=space.id,
            payload={"name": space.name},
        )
        return space

    @transactional
    def create_project(
        self,
        *,
        user_id: uuid.UUID,
        space_id: uuid.UUID,
        name: str,
        description: str | None = None,
        learning_goal: str | None = None,
    ) -> Project:
        space = self.spaces.get_for_user(space_id, user_id)
        if space is None:
            raise NotFoundError("Space not found")
        project = self.projects.create(
            space_id=space.id,
            owner_id=space.owner_id,  # inherit — never trust caller-supplied owner
            name=name,
            description=description,
            learning_goal=learning_goal,
        )
        self.session.flush()
        self.events.append(
            event_type=EventType.PROJECT_CREATED,
            user_id=user_id,
            project_id=project.id,
            entity_type="project",
            entity_id=project.id,
            payload={"name": project.name, "space_id": str(space.id)},
        )
        return project

    @transactional
    def update_space(
        self,
        *,
        user_id: uuid.UUID,
        space_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> Space:
        space = self.spaces.get_for_user(space_id, user_id)
        if space is None:
            raise NotFoundError("Space not found.")
        if name is not None:
            if not name.strip():
                raise BadRequestError("Space name must not be blank.")
            space.name = name.strip()
        if description is not None:
            space.description = description
        return space

    @transactional
    def set_space_archived(
        self, *, user_id: uuid.UUID, space_id: uuid.UUID, archived: bool
    ) -> Space:
        space = self.spaces.get_for_user(space_id, user_id, include_archived=True)
        if space is None:
            raise NotFoundError("Space not found.")
        space.archived_at = utcnow() if archived else None
        return space

    @transactional
    def update_project(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        learning_goal: str | None = None,
        target_outcome: str | None = None,
        difficulty: Difficulty | None = None,
    ) -> Project:
        """Only explicit metadata fields are writable — never owner/space/ids/metrics."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        if name is not None:
            if not name.strip():
                raise BadRequestError("Project name must not be blank.")
            project.name = name.strip()
        if description is not None:
            project.description = description
        if learning_goal is not None:
            project.learning_goal = learning_goal
        if target_outcome is not None:
            project.target_outcome = target_outcome
        if difficulty is not None:
            project.difficulty = difficulty
        return project

    @transactional
    def set_project_archived(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, archived: bool
    ) -> Project:
        project = self.projects.get_for_user(project_id, user_id, include_archived=True)
        if project is None:
            raise NotFoundError("Project not found.")
        project.archived_at = utcnow() if archived else None
        return project

    def get_space_detail(self, *, user_id: uuid.UUID, space_id: uuid.UUID) -> tuple[Space, int]:
        """Space plus its active project count (single extra GROUP BY query)."""
        space = self.spaces.get_for_user(space_id, user_id)
        if space is None:
            raise NotFoundError("Space not found.")
        counts = self.spaces.count_projects_for_spaces(user_id, [space.id])
        return space, counts.get(space.id, 0)

    def get_project_detail(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> tuple[Project, int]:
        """Project plus its active material count (single extra GROUP BY query)."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        counts = self.projects.count_materials_for_projects([project.id])
        return project, counts.get(project.id, 0)

    def require_project(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        """Entry gate for every project-scoped operation downstream.

        404 (not 403) on mismatch so resource existence is never disclosed
        across tenant boundaries.
        """
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project
