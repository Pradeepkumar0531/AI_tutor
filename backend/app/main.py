"""FastAPI application factory: middleware, CORS, logging, errors, versioned routing."""

from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, request_id_var

configure_logging()
log = logging.getLogger("app")

# Incoming request IDs are echoed into logs + responses: accept only tight
# token shapes, otherwise mint one ( unbounded/malicious values must not flow
# into structured logs or response headers).
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _request_id(raw: str | None) -> str:
    if raw and _REQUEST_ID_RE.match(raw):
        return raw
    return uuid.uuid4().hex[:16]


def create_app() -> FastAPI:
    settings = get_settings()
    show_docs = settings.enable_api_docs or not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        description="AI-powered learning platform API (modular monolith foundation).",
        version="0.1.0",
        docs_url="/docs" if show_docs else None,
        openapi_url="/openapi.json" if show_docs else None,
    )

    @app.middleware("http")
    async def _request_id_and_logging(request, call_next):  # type: ignore[no-untyped-def]
        rid = _request_id(request.headers.get("X-Request-ID"))
        request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error method=%s path=%s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Internal server error",
                        "details": None,
                        "request_id": rid,
                    }
                },
            )
        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-ID"] = rid
        log.info(
            "method=%s path=%s status=%s duration_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
