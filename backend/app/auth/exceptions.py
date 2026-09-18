"""Auth-specific errors, all funneled through the shared error envelope."""

from __future__ import annotations

from app.core.exceptions import ForbiddenError, UnauthorizedError


class InvalidCredentialsError(UnauthorizedError):
    code = "INVALID_CREDENTIALS"
    message = "Invalid email or password."


class AccountDisabledError(ForbiddenError):
    code = "ACCOUNT_DISABLED"
    message = "This account has been disabled."
