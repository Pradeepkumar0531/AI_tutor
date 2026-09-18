"""Password policy + Argon2id hashing/verification.

The hash implementation itself lives in ``app.core.security`` (single source);
this module adds the centralized policy so it can evolve in one place.
"""

from __future__ import annotations

from app.core.security import hash_password, verify_password  # noqa: F401  (re-export)

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def validate_password(password: str) -> str:
    """Enforce the policy; return the password unchanged on success.

    Never stripped or truncated: leading/trailing whitespace is part of the
    password. Raises ``ValueError`` (mapped to 422 by request schemas and to
    400 by the service layer).
    """
    if not isinstance(password, str) or not password.strip():
        raise ValueError("Password must not be empty.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    return password
