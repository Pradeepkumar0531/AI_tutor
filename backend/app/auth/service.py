"""Auth service: registration, login, logout auditing. Route -> Service -> Repo -> DB.

Security notes:
- Login failures always return the generic "Invalid email or password", whether the
  email is unknown, the password is wrong, or the account is disabled (no enumeration).
- Event payloads never contain passwords, hashes, or tokens — only outcome + user id.
- Structured logs carry outcome + user id on success, outcome only on failure.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import NoReturn

from sqlalchemy.orm import Session

from app.auth.exceptions import InvalidCredentialsError
from app.auth.password import hash_password, validate_password, verify_password
from app.auth.schemas import AuthResponse, UserProfile
from app.auth.tokens import issue_access_token
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, ConflictError, RateLimitedError
from app.models.enums import EventType
from app.models.mixins import utcnow
from app.models.users import User
from app.repositories.intelligence import EventRepository
from app.repositories.projects import UserRepository
from app.services.base import BaseService, transactional

log = logging.getLogger("app.auth")

# Precomputed dummy Argon2 hash for unknown-email logins: verifying against it
# costs ~100ms like a real check, closing the timing gap that would otherwise
# distinguish "unknown email" (fast) from "wrong password" (slow). The secret
# is random and unrecoverable from the hash — it can never authenticate anyone.
_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$tWw17B4iGoTBp4vKZSSi3w"
    "$+thXac7dG05+UUhphgb3bFT6HMg8R4cUN14z8bnGmuM"
)

# In-process sliding window of failed logins per normalized email:
# {email: [monotonic timestamps]}. Bounded (pruned on every check); gateway
# IP limiting remains a deployment concern (see docs/DEPLOYMENT.md).
_FAILED_LOGINS: dict[str, list[float]] = {}
_FAILED_LOGINS_LOCK = threading.Lock()
_MAX_TRACKED_EMAILS = 10000

#: Minimal RBAC roles. 'admin' unlocks /api/v1/admin/* via require_admin.
VALID_ROLES = frozenset({"learner", "admin"})


def _apply_admin_bootstrap(user: User) -> None:
    """Promote bootstrap admins (ADMIN_EMAILS) on register/login.

    The only privilege-escalation path: env-configured emails, no public
    endpoint. Idempotent — a no-op for non-listed emails and existing admins.
    """
    if user.role == "admin":
        return
    if user.email in get_settings().admin_email_list:
        user.role = "admin"
        log.info("admin bootstrap promotion user_id=%s", user.id)


def _throttle_check(email: str) -> None:
    """Raise 429 when this email recently failed too often. Success paths
    clear the counter (see _throttle_clear)."""
    settings = get_settings()
    now = time.monotonic()
    window = settings.login_attempt_window_seconds
    limit = settings.login_max_attempts
    with _FAILED_LOGINS_LOCK:
        attempts = [t for t in _FAILED_LOGINS.get(email, []) if now - t < window]
        if len(_FAILED_LOGINS) > _MAX_TRACKED_EMAILS:
            _FAILED_LOGINS.clear()
        _FAILED_LOGINS[email] = attempts
        if len(attempts) >= limit:
            raise RateLimitedError(
                details={"retry_after_seconds": int(window)},
            )


def _throttle_note_failure(email: str) -> None:
    with _FAILED_LOGINS_LOCK:
        _FAILED_LOGINS.setdefault(email, []).append(time.monotonic())


def _throttle_clear(email: str) -> None:
    with _FAILED_LOGINS_LOCK:
        _FAILED_LOGINS.pop(email, None)


class AuthService(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.users = UserRepository(session)
        self.events = EventRepository(session)

    @transactional
    def register(self, *, email: str, password: str, display_name: str) -> AuthResponse:
        try:
            validate_password(password)
        except ValueError as e:
            raise BadRequestError(str(e)) from e
        normalized = User.normalize_email(email)
        if self.users.get_by_email(normalized) is not None:
            raise ConflictError("An account with this email already exists.")
        user = self.users.create(
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name.strip(),
        )
        _apply_admin_bootstrap(user)
        self.session.flush()  # id needed for the event row below
        self.events.append(
            event_type=EventType.USER_REGISTERED,
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        issued = issue_access_token(user.id)
        log.info("register ok user_id=%s", user.id)
        return AuthResponse(
            access_token=issued["access_token"],
            token_type=issued["token_type"],
            expires_in=issued["expires_in"],
            user=UserProfile.model_validate(user),
        )

    def _login_failed(self, email: str) -> NoReturn:
        # Generic failure in all cases: no account enumeration. The attempt
        # counts toward brute-force throttling.
        _throttle_note_failure(email)
        self.events.append(event_type=EventType.USER_LOGIN_FAILED)
        log.info("login failed")
        raise InvalidCredentialsError()

    @transactional
    def login(self, *, email: str, password: str) -> AuthResponse:
        normalized = User.normalize_email(email)
        _throttle_check(normalized)
        user = self.users.get_by_email(normalized)
        if user is None:
            # Same-cost dummy verification: unknown emails take as long as
            # wrong passwords, so timing reveals nothing about existence.
            verify_password(password, _DUMMY_HASH)
            self._login_failed(normalized)
        if not user.is_active or not verify_password(password, user.password_hash):
            self._login_failed(normalized)
        _throttle_clear(normalized)
        user.last_login_at = utcnow()
        _apply_admin_bootstrap(user)
        self.session.flush()
        self.events.append(
            event_type=EventType.USER_LOGIN_SUCCEEDED,
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        issued = issue_access_token(user.id)
        log.info("login ok user_id=%s", user.id)
        return AuthResponse(
            access_token=issued["access_token"],
            token_type=issued["token_type"],
            expires_in=issued["expires_in"],
            user=UserProfile.model_validate(user),
        )

    @transactional
    def logout(self, *, user: User) -> None:
        # Stateless short-lived JWT: nothing to revoke server-side. The audit event
        # records the logout; the client drops the token (see docs/SECURITY.md).
        self.events.append(
            event_type=EventType.USER_LOGOUT,
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )
        log.info("logout ok user_id=%s", user.id)
