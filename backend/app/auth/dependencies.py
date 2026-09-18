"""FastAPI auth dependencies: exactly one place parses/validates tokens.

- 401 (``UnauthorizedError``): missing, invalid, expired, wrong-type, or
  subject-less token; token for a nonexistent user.
- 403 (``AccountDisabledError``): valid token, disabled account.
- 404 (``NotFoundError``): resource not owned by the caller — existence is never
  disclosed across tenant boundaries (IDOR protection).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.exceptions import AccountDisabledError
from app.auth.tokens import decode_access_token
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.db.session import get_db
from app.models.learning import Project, Space
from app.models.users import User
from app.repositories.projects import ProjectRepository, SpaceRepository

_bearer = HTTPBearer(auto_error=False)

Credentials = Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)]
SessionDep = Annotated[Session, Depends(get_db)]


async def get_current_user(creds: Credentials, session: SessionDep) -> User:
    if creds is None or not creds.credentials:
        raise UnauthorizedError("Not authenticated.")
    claims = decode_access_token(creds.credentials)
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError as e:
        raise UnauthorizedError("Invalid token subject.") from e
    user = session.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Invalid or expired token.")
    if not user.is_active:
        raise AccountDisabledError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    """Server-side admin gate for /api/v1/admin/*. Frontend role-hiding is
    cosmetic only — every admin route depends on this. Learners (and unknown
    roles) get 403; unauthenticated/disabled are rejected upstream."""
    if user.role != "admin":
        raise ForbiddenError("Admin access required.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def get_owned_space(space_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Space:
    space = SpaceRepository(session).get_for_user(space_id, user.id)
    if space is None:
        raise NotFoundError("Space not found.")
    return space


async def get_owned_project(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Project:
    project = ProjectRepository(session).get_for_user(project_id, user.id)
    if project is None:
        raise NotFoundError("Project not found.")
    return project
