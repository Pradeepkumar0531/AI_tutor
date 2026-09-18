"""Application exception hierarchy + consistent error envelope."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DisconnectionError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id, logger


class AppError(Exception):
    code: str = "INTERNAL_ERROR"
    message: str = "Internal server error"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    details: Any = None

    def __init__(self, message: str | None = None, details: Any = None) -> None:
        if message:
            self.message = message
        if details is not None:
            self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "RESOURCE_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(AppError):
    code = "RESOURCE_CONFLICT"
    status_code = status.HTTP_409_CONFLICT


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    status_code = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = status.HTTP_403_FORBIDDEN


class BadRequestError(AppError):
    code = "BAD_REQUEST"
    status_code = status.HTTP_400_BAD_REQUEST


class ServiceUnavailableError(AppError):
    code = "SERVICE_UNAVAILABLE"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, message: str | None = None, details: Any = None) -> None:
        super().__init__(message or "Too many requests. Please wait and try again.", details)


def error_envelope(code: str, message: str, details: Any, request_id: str) -> dict:
    return {
        "error": {"code": code, "message": message, "details": details, "request_id": request_id}
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.code, exc.message, exc.details, get_request_id()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(code, str(exc.detail), None, get_request_id()),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # exc.errors() carries non-JSON-serializable context (e.g. ValueError
        # instances) and long pydantic doc URLs — sanitize before enveloping.
        details = []
        for err in exc.errors():
            clean = {k: v for k, v in err.items() if k != "url"}
            if isinstance(clean.get("ctx"), dict):
                clean["ctx"] = {k: str(v) for k, v in clean["ctx"].items()}
            details.append(clean)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_envelope(
                "VALIDATION_ERROR", "Request validation failed", details, get_request_id()
            ),
        )

    async def _database_unavailable(request: Request, exc: Exception) -> JSONResponse:
        # Infrastructure connectivity only (DNS, refused/timed-out connections,
        # lost connections). Deliberately NOT the whole DBAPIError family:
        # query-time failures such as IntegrityError stay on the generic 500
        # path. Full detail (hostname, traceback) stays server-side in the log
        # with request-ID correlation; clients get a safe 503 envelope.
        logger.exception(
            "database unavailable method=%s path=%s err=%s",
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_envelope(
                "SERVICE_UNAVAILABLE",
                "The service is temporarily unavailable. Please try again.",
                None,
                get_request_id(),
            ),
        )

    # FastAPI's exception_handler takes a single class: register the same
    # mapping for each connectivity failure type.
    app.exception_handler(OperationalError)(_database_unavailable)
    app.exception_handler(DisconnectionError)(_database_unavailable)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:  # noqa: BLE001
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope(
                "INTERNAL_ERROR", "Internal server error", None, get_request_id()
            ),
        )
