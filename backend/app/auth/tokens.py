"""JWT access tokens: minimal claims (sub/typ/iat/exp/jti), strict validation.

``app.core.security`` delegates here so there is exactly one token implementation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError

ACCESS_TOKEN_TYPE = "access"

_DEFAULT_DEV_SECRET = "change-me-jwt"

# Known placeholder/example secrets that must never sign production tokens.
# Includes the Settings default and the backend/.env.example placeholder
# (which is long enough to pass the length check on its own).
_BLOCKED_PROD_SECRETS = frozenset(
    {
        "change-me-jwt",
        "change-me-generate-a-long-jwt-secret",
        "changeme",
        "secret",
        "password",
        "test",
        "test-secret",
        "development",
        "insecure",
    }
)


def require_jwt_secret(settings: Settings | None = None) -> str:
    """Fail clearly when auth is used without a real secret in production."""
    s = settings or get_settings()
    secret = s.jwt_secret_key
    normalized = (secret or "").strip().lower()
    if s.is_production and (
        not normalized or normalized in _BLOCKED_PROD_SECRETS or len(secret) < 32
    ):
        raise RuntimeError(
            "JWT_SECRET_KEY is not configured for production: set a random value "
            "of at least 32 characters."
        )
    return secret


def issue_access_token(user_id: uuid.UUID | str, settings: Settings | None = None) -> dict:
    """Issue a short-lived access token; return token + metadata for responses."""
    s = settings or get_settings()
    secret = require_jwt_secret(s)
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=s.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": uuid.uuid4().hex,  # unique id for auditing / future revocation
    }
    token = jwt.encode(payload, secret, algorithm=s.jwt_algorithm)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": s.access_token_expire_minutes * 60,
    }


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Decode + validate signature, expiry, type, and subject. Never silent."""
    s = settings or get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm])
    except jwt.ExpiredSignatureError as e:
        raise UnauthorizedError("Token has expired.") from e
    except jwt.PyJWTError as e:
        raise UnauthorizedError("Invalid or expired token.") from e
    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        raise UnauthorizedError("Invalid token type.")
    if not claims.get("sub"):
        raise UnauthorizedError("Token is missing its subject.")
    return claims
