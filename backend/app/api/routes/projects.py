"""Project endpoints. Ownership chain verified before any data is returned."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_owned_project
from app.db.session import get_db
from app.models.learning import Project
from app.models.users import User
from app.repositories.projects import ProjectRepository
from app.schemas.common import Page
from app.schemas.spaces import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]


def _to_read(project: Project, material_count: int | None = None) -> ProjectRead:
    read = ProjectRead.model_validate(project)
    read.material_count = material_count
    return read


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, user: CurrentUser, session: SessionDep) -> ProjectRead:
    project = ProjectService(session).create_project(
        user_id=user.id,
        space_id=body.space_id,
        name=body.name,
        description=body.description,
        learning_goal=body.learning_goal,
    )
    return _to_read(project, 0)


@router.get("", response_model=Page[ProjectRead])
def list_projects(
    user: CurrentUser,
    session: SessionDep,
    space_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=160)] = None,
    include_archived: Annotated[bool, Query()] = False,
) -> Page[ProjectRead]:
    repo = ProjectRepository(session)
    if space_id is not None:
        # Owner filter inside the repository keeps another user's space opaque:
        # it simply yields zero rows, never its contents.
        items, total = repo.list_for_space(
            space_id,
            user.id,
            page=page,
            page_size=page_size,
            search=search,
            include_archived=include_archived,
        )
    else:
        items, total = repo.list_for_user(
            user.id,
            page=page,
            page_size=page_size,
            search=search,
            include_archived=include_archived,
        )
    counts = repo.count_materials_for_projects([p.id for p in items])
    return Page[ProjectRead](
        items=[_to_read(p, counts.get(p.id, 0)) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project: OwnedProject, user: CurrentUser, session: SessionDep) -> ProjectRead:
    fresh, count = ProjectService(session).get_project_detail(
        user_id=user.id, project_id=project.id
    )
    return _to_read(fresh, count)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    body: ProjectUpdate, project: OwnedProject, user: CurrentUser, session: SessionDep
) -> ProjectRead:
    updated = ProjectService(session).update_project(
        user_id=user.id,
        project_id=project.id,
        name=body.name,
        description=body.description,
        learning_goal=body.learning_goal,
        target_outcome=body.target_outcome,
        difficulty=body.difficulty,
    )
    return _to_read(updated)


@router.delete("/{project_id}", response_model=ProjectRead)
def archive_project(project: OwnedProject, user: CurrentUser, session: SessionDep) -> ProjectRead:
    """Archive (soft-delete). Rows and all future children are kept; restore reverses it."""
    archived = ProjectService(session).set_project_archived(
        user_id=user.id, project_id=project.id, archived=True
    )
    return _to_read(archived)


@router.post("/{project_id}/restore", response_model=ProjectRead)
def restore_project(project_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> ProjectRead:
    # Resolved inside the service with archived rows included (see spaces restore).
    restored = ProjectService(session).set_project_archived(
        user_id=user.id, project_id=project_id, archived=False
    )
    return _to_read(restored)
