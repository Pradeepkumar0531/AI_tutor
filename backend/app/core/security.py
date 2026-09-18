"""Security boundaries: Argon2id hashing + JWT tokens + legacy auth dependency.

The canonical token implementation lives in ``app.auth.tokens`` (claims
sub/typ/iat/exp/jti, strict validation); the helpers below delegate so there is
exactly one JWT code path. ``hash_password``/``verify_password`` remain the single
hashing implementation, re-exported by ``app.auth.password`` alongside the policy.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError
from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.tokens import decode_access_token as _decode_strict
from app.auth.tokens import issue_access_token
from app.core.config import Settings
from app.core.exceptions import UnauthorizedError

_ph = PasswordHasher()  # defaults to Argon2id
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        # Wrong password AND corrupt stored hash both mean "not verified" —
        # callers already map False to a generic auth failure.
        return False


def create_access_token(subject: str, settings: Settings | None = None) -> str:
    return str(issue_access_token(subject, settings)["access_token"])


def decode_access_token(token: str, settings: Settings | None = None) -> dict:
    return dict(_decode_strict(token, settings))


async def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> str:
    if creds is None or not creds.credentials:
        raise UnauthorizedError(
            "Not authenticated", details={"status": status.HTTP_401_UNAUTHORIZED}
        )
    claims = _decode_strict(creds.credentials)
    return str(claims["sub"])
