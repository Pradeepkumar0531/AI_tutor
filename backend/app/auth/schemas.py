"""Auth request/response schemas. No password hashes, no tokens in logs, ever."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.auth.password import MAX_PASSWORD_LENGTH, validate_password


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def _policy(cls, v: str) -> str:
        return validate_password(v)


class LoginRequest(BaseModel):
    # Deliberately no policy validator here: login must accept whatever the user
    # originally registered so policy changes never lock anyone out.
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserProfile(BaseModel):
    """Safe public profile for /me and auth responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: str = "learner"
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


class LogoutResponse(BaseModel):
    ok: bool = True
