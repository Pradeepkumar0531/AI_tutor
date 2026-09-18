"""Auth endpoints: register / login / logout / me. No business logic here."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    AuthResponse,
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    UserProfile,
)
from app.auth.service import AuthService
from app.db.session import get_db
from app.models.users import User

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, session: SessionDep) -> AuthResponse:
    return AuthService(session).register(
        email=str(body.email), password=body.password, display_name=body.display_name
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, session: SessionDep) -> AuthResponse:
    return AuthService(session).login(email=str(body.email), password=body.password)


@router.post("/logout", response_model=LogoutResponse)
def logout(user: CurrentUser, session: SessionDep) -> LogoutResponse:
    AuthService(session).logout(user=user)
    return LogoutResponse()


@router.get("/me", response_model=UserProfile)
def me(user: CurrentUser) -> User:
    return user
