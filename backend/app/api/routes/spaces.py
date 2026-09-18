"""Space endpoints. Every read/write is ownership-scoped; misses are 404."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_owned_space
from app.db.session import get_db
from app.models.learning import Space
from app.models.users import User
from app.repositories.projects import SpaceRepository
from app.schemas.common import Page
from app.schemas.spaces import SpaceCreate, SpaceRead, SpaceUpdate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/spaces", tags=["spaces"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
OwnedSpace = Annotated[Space, Depends(get_owned_space)]


def _to_read(space: Space, project_count: int | None = None) -> SpaceRead:
    read = SpaceRead.model_validate(space)
    read.project_count = project_count
    return read


@router.post("", response_model=SpaceRead, status_code=status.HTTP_201_CREATED)
def create_space(body: SpaceCreate, user: CurrentUser, session: SessionDep) -> SpaceRead:
    space = ProjectService(session).create_space(
        owner_id=user.id, name=body.name, description=body.description
    )
    return _to_read(space, 0)


@router.get("", response_model=Page[SpaceRead])
def list_spaces(
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=120)] = None,
    include_archived: Annotated[bool, Query()] = False,
) -> Page[SpaceRead]:
    repo = SpaceRepository(session)
    items, total = repo.list_for_user(
        user.id,
        page=page,
        page_size=page_size,
        search=search,
        include_archived=include_archived,
    )
    counts = repo.count_projects_for_spaces(user.id, [s.id for s in items])
    return Page[SpaceRead](
        items=[_to_read(s, counts.get(s.id, 0)) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{space_id}", response_model=SpaceRead)
def get_space(space: OwnedSpace, user: CurrentUser, session: SessionDep) -> SpaceRead:
    # Re-resolve through the service so the count query shares the same scope.
    fresh, count = ProjectService(session).get_space_detail(user_id=user.id, space_id=space.id)
    return _to_read(fresh, count)


@router.patch("/{space_id}", response_model=SpaceRead)
def update_space(
    body: SpaceUpdate, space: OwnedSpace, user: CurrentUser, session: SessionDep
) -> SpaceRead:
    updated = ProjectService(session).update_space(
        user_id=user.id, space_id=space.id, name=body.name, description=body.description
    )
    return _to_read(updated)


@router.delete("/{space_id}", response_model=SpaceRead)
def archive_space(space: OwnedSpace, user: CurrentUser, session: SessionDep) -> SpaceRead:
    """Archive (soft-delete). Rows are kept; restore reverses it. No hard deletes."""
    archived = ProjectService(session).set_space_archived(
        user_id=user.id, space_id=space.id, archived=True
    )
    return _to_read(archived)


@router.post("/{space_id}/restore", response_model=SpaceRead)
def restore_space(space_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> SpaceRead:
    # Resolved inside the service with archived rows included: the ownership
    # dependency above only sees active rows, which would 404 an archived space.
    restored = ProjectService(session).set_space_archived(
        user_id=user.id, space_id=space_id, archived=False
    )
    return _to_read(restored)
